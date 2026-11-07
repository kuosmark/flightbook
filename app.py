"""Flightbook's server-rendered web application."""

from datetime import date, timedelta
import os
import re
import secrets
import sqlite3

import click
from flask import Flask, abort, g, redirect, render_template, request, session, url_for

import db
from session_key import load_key
import users
import flights

app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_key(app.instance_path),
    DATABASE=os.path.join(app.root_path, "flightbook.db"),
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLIGHTBOOK_COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=16 * 1024,
)
app.teardown_appcontext(db.close_connection)


@app.cli.command("init-db")
def init_db_command():
    """Prepare local session signing and initialize the database."""
    if not app.secret_key:
        app.secret_key = load_key(app.instance_path, create=True)
    db.init_db()
    click.echo("Database initialized.")


@app.before_request
def load_session():
    """Load the current account and protect state-changing requests."""
    if not app.secret_key:
        raise RuntimeError("Run init-db or set FLIGHTBOOK_SECRET_KEY before starting Flightbook.")
    g.user = None
    if "user_id" in session:
        g.user = users.get_user(session["user_id"])
        if g.user is None:
            session.clear()
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(
            expected.encode("utf-8"), supplied.encode("utf-8")
        ):
            abort(403, description="Form expired. Go back, refresh the form, and try again.")
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)


def start_session(user_id):
    """Replace the anonymous session with a seven-day renewable login."""
    session.clear()
    session["user_id"] = user_id
    session.permanent = True
    session["csrf_token"] = secrets.token_hex(32)


def registration_error(username, password, confirmation):
    """Validate the agreed account rules on the server."""
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        return "Use 3–30 letters (A–Z), numbers, or underscores for your username."
    if not 15 <= len(password) <= 128:
        return "Use 15–128 characters for your password."
    if password != confirmation:
        return "The passwords do not match."
    return None


@app.route("/")
def index():
    """Show the public flight diary homepage."""
    return flight_listing()


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create an account and sign in immediately."""
    if g.user is not None:
        return redirect(url_for("index"))
    username = ""
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "")
        error = registration_error(username, password, confirmation)
        if error is None:
            try:
                user_id = users.create_user(username, password)
            except sqlite3.IntegrityError:
                error = "That username is already taken."
            else:
                start_session(user_id)
                return redirect(url_for("index"))
    return render_template("register.html", username=username, error=error), 400 if error else 200


@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate without requiring the username's original capitalization."""
    if g.user is not None:
        return redirect(url_for("index"))
    username = ""
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_id = None
        if re.fullmatch(r"[A-Za-z0-9_]{3,30}", username) and 15 <= len(password) <= 128:
            user_id = users.authenticate(username, password)
        if user_id is not None:
            start_session(user_id)
            return redirect(url_for("index"))
        error = "Incorrect username or password."
    return render_template("login.html", username=username, error=error), 400 if error else 200


@app.post("/logout")
def logout():
    """Clear the browser's login session."""
    session.clear()
    return redirect(url_for("index"))


def airport_picker(data, values, field_labels, context=None):
    """Resolve an explicit picker action without writing the draft or changing its scope."""
    field = data.get("find")
    if field not in field_labels:
        abort(400)
    if "cancel_find" in data:
        return None, {}
    if "pick" in data:
        code = data["pick"]
        names = flights.airport_names((code, code))
        if code not in names:
            abort(400)
        values[field] = code
        return None, {field: names[code]}
    query = data.get("q", "").strip()
    matches = flights.find_airports(query) if 2 <= len(query) <= 100 else []
    return render_template("airport_picker.html", field=field, label=field_labels[field],
                           values=values | (context or {}), query=query, searched="q" in data,
                           matches=matches[:flights.AIRPORT_RESULT_LIMIT],
                           more=len(matches) > flights.AIRPORT_RESULT_LIMIT), {}


@app.template_filter("flight_date")
def flight_date(value):
    """Display an ISO departure date without a leading zero on the day."""
    day = date.fromisoformat(value)
    return f"{day.day} {day:%b %Y}"


def return_to_search(previous, draft, picked):
    """Redirect to the applied list; carry unfinished fields for this return only."""
    filters, _ = flights.search_filters(previous)
    if previous.get("page", "1") != "1":
        filters["page"] = previous["page"]
    target = url_for(request.endpoint, **(filters or {"filter": "1"}))
    field = request.args["find"]
    # A normal draft is at most 113 characters; do not put oversized input in a cookie.
    if sum(map(len, draft.values())) > 256:
        abort(400)
    session["airport_return"] = {"target": target, "draft": draft, "picked": picked,
                                 "field": field}
    return redirect(target + "#" + field, code=303)


def applied_filter_labels(filters):
    """Describe the submitted filters in form order, resolving airport codes together."""
    names = flights.airport_names((filters.get("from"), filters.get("to"))) if filters else {}
    labels = []
    for key, label in (("from", "From"), ("to", "To"), ("airline", "Airline"),
                       ("flight_number", "Flight number")):
        if key in filters:
            value = filters[key]
            if key in ("from", "to"):
                value = f"{names.get(value, 'Unlisted airport')} ({value})"
            labels.append((label, value))
    return labels


def flight_listing(user_id=None):
    """Render either recent public entries or the current user's flight history."""
    draft, errors = flights.search_filters(request.args)
    filters = draft
    focus = None
    picked = {}
    if "find" in request.args:
        # The finder carries the last submitted search separately from unfinished edits.
        previous = {key.removeprefix("applied_"): value for key, value in request.args.items()
                    if key.startswith("applied_")}
        filters, errors = flights.search_filters(previous)
        context = {"applied_" + key: value for key, value in filters.items()}
        context["applied_page"] = previous.get("page", "1")
        picker, picked = airport_picker(
            request.args, draft, {"from": "departure", "to": "arrival"}, context)
        if picker:
            return picker
        return return_to_search(previous, draft, picked)
    if "applied_page" in request.args:
        # Keep submitted searches bookmarkable without the finder's hidden fields.
        return redirect(url_for(request.endpoint, **(draft or {"filter": "1"})))
    page_value = request.args.get("page", "1")
    pending = session.get("airport_return")
    if pending and pending["target"] == request.full_path.rstrip("?"):
        session.pop("airport_return")
        draft, picked, focus = pending["draft"], pending["picked"], pending["field"]
    try:
        page = int(page_value)
    except ValueError:
        abort(404)
    if not 1 <= page <= 1000000:
        abort(404)
    filters_open = bool(filters or draft or focus or request.args.get("filter") == "1")
    entries, total = ([], 0) if errors else flights.list_flights(page, filters, user_id)
    if page > 1 and not entries and not errors:
        abort(404)
    return render_template("index.html", entries=entries, page=page,
                           pagination=flight_pagination(page, total),
                           return_params=list_return_params(page, filters, user_id),
                           mine=user_id is not None,
                           filters=filters, draft=draft, errors=errors,
                           filters_open=filters_open, picked=picked, focus=focus,
                           applied_filters=applied_filter_labels(filters) if not errors else []), (
                               400 if errors else 200)


def list_return_params(page, filters, user_id):
    """Carry the list scope, page and filters when a traveller opens an entry."""
    params = {}
    if user_id is not None:
        params["scope"] = "mine"
    if page > 1:
        params["page"] = page
    return params | filters


def flight_pagination(page, total):
    """Build a small window of links regardless of the size of the diary."""
    size = flights.PAGE_SIZE
    last = (total + size - 1) // size
    numbers = sorted({1, last, *range(max(1, page - 1), min(last, page + 1) + 1)})
    pages = []
    for number in numbers:
        if pages and number > pages[-1] + 1:
            pages.append(number - 1 if number == pages[-1] + 2 else None)
        pages.append(number)
    return {"start": (page - 1) * size + 1, "end": min(page * size, total),
            "total": total, "last": last, "pages": pages}


def require_login():
    """Require an account for personal pages and changes."""
    if g.user is None:
        abort(401, description="Log in to manage your flights.")


def find_flight(flight_id, owner=False):
    """Look up a flight and optionally require its owner."""
    entry = flights.get_flight(flight_id)
    if entry is None:
        abort(404)
    if owner:
        require_login()
        if entry["user_id"] != g.user["id"]:
            abort(403)
    return entry


@app.get("/my-flights")
def my_flights():
    """Show the signed-in traveller's history."""
    require_login()
    return flight_listing(g.user["id"])


@app.get("/flights/<int:flight_id>")
def flight_detail(flight_id):
    """Show a flight to any visitor."""
    mine = request.args.get("scope") == "mine"
    filters, _ = flights.search_filters(request.args)
    page = request.args.get("page", 1, type=int)
    back_url = url_for("my_flights" if mine else "index", page=page if page > 1 else None,
                       _anchor=f"flight-{flight_id}", **filters)
    return render_template("flight.html", flight=find_flight(flight_id),
                           mine=mine, back_url=back_url)


def flight_form(entry=None):
    """Share creation and editing validation and rendering."""
    require_login()
    values = {field: str(entry[field] or "") if entry else "" for field in flights.FIELDS}
    if request.method == "POST":
        values = flights.form_values(request.form)
    picked = {}
    if "find" in request.form:
        picker, picked = airport_picker(
            request.form, values, {"departure_code": "departure", "arrival_code": "arrival"})
        if picker:
            return picker
        action = "route"
    else:
        action = request.form.get("action", "details" if entry is not None
                                  and request.method == "GET" else "route")
    if action not in ("route", "continue", "details", "save"):
        abort(400)
    errors = flights.route_errors(values) if action != "route" else {}
    details = action != "route" and not errors
    names = (flights.airport_names((values["departure_code"], values["arrival_code"]))
             if details else {})
    cabins = flights.choices("cabin") if details else []
    purposes = flights.choices("purpose") if details else []
    if details and action == "save":
        errors = flights.detail_errors(values, cabins, purposes)
        for field in ("departure_code", "arrival_code"):
            if values[field] not in names and request.form.get("confirm_" + field) != values[field]:
                errors[field] = "Confirm the unlisted code or change the route."
        if not errors:
            flight_id = flights.save(values, g.user["id"], entry["id"] if entry else None)
            return redirect(url_for("flight_detail", flight_id=flight_id))
    hidden_keys = flights.ROUTE_FIELDS if details else flights.DETAIL_FIELDS
    hidden_fields = {key: values[key] for key in hidden_keys}
    return render_template("flight_form.html", hidden_fields=hidden_fields, values=values,
                           errors=errors, names=names,
                           details=details, editing=entry is not None, cabins=cabins,
                           purposes=purposes, today=date.today().isoformat(), picked=picked), (
                               400 if errors else 200)


@app.route("/flights/new", methods=["GET", "POST"])
def new_flight():
    """Create a public diary entry."""
    return flight_form()


@app.route("/flights/<int:flight_id>/edit", methods=["GET", "POST"])
def edit_flight(flight_id):
    """Edit an owned flight."""
    return flight_form(find_flight(flight_id, owner=True))


@app.route("/flights/<int:flight_id>/delete", methods=["GET", "POST"])
def delete_flight(flight_id):
    """Confirm deletion before accepting the protected POST."""
    entry = find_flight(flight_id, owner=True)
    if request.method == "POST":
        flights.delete(flight_id, g.user["id"])
        return redirect(url_for("my_flights"))
    return render_template("delete_flight.html", flight=entry)
