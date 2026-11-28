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
import reviews

# SQLite stores integers as signed 64-bit values.
SQLITE_MAX_INTEGER = 2**63 - 1

app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_key(app.instance_path),
    DATABASE=os.path.join(app.root_path, "flightbook.db"),
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLIGHTBOOK_COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=128 * 1024,
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
    target = flight_list_url(**(filters or {"filter": "1"}))
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


@app.template_global()
def flight_list_url(**params):
    """Keep route parameters when linking within a public or personal flight list."""
    return url_for(request.endpoint, **(request.view_args or {}), **params)


def find_filter_airport(draft):
    """Keep the applied search separate while choosing an airport for its draft."""
    previous = {key.removeprefix("applied_"): value for key, value in request.args.items()
                if key.startswith("applied_")}
    filters, _ = flights.search_filters(previous)
    context = {"applied_" + key: value for key, value in filters.items()}
    context["applied_page"] = previous.get("page", "1")
    picker, picked = airport_picker(
        request.args, draft, {"from": "departure", "to": "arrival"}, context)
    if picker:
        return picker
    return return_to_search(previous, draft, picked)


def flight_listing(user_id=None, profile=None):
    """Render a public feed, personal diary, or traveller's flight history."""
    draft, errors = flights.search_filters(request.args)
    filters = draft
    focus = None
    picked = {}
    if "find" in request.args:
        return find_filter_airport(draft)
    if "applied_page" in request.args:
        # Keep submitted searches bookmarkable without the finder's hidden fields.
        return redirect(flight_list_url(**(draft or {"filter": "1"})))
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
    statistics = {}
    if profile is not None:
        year = date.today().year
        statistics = {"total": flights.count_flights({}, user_id),
                      "this_year": flights.flights_in_year(user_id, year),
                      "ratings": flights.rating_statistics(user_id),
                      "airports": flights.airport_count(user_id),
                      "top_airports": flights.top_airports(user_id), "year": year}
    return render_template("profile.html" if profile is not None else "index.html",
                           entries=entries, page=page, profile=profile, statistics=statistics,
                           pagination=flight_pagination(page, total),
                           return_params=list_return_params(page, filters, user_id, profile),
                           mine=user_id is not None and profile is None,
                           filters=filters, draft=draft, errors=errors,
                           filters_open=filters_open, picked=picked, focus=focus,
                           applied_filters=applied_filter_labels(filters) if not errors else []), (
                               400 if errors else 200)


def list_return_params(page, filters, user_id, profile=None):
    """Carry the list scope, page and filters when a traveller opens an entry."""
    params = {}
    if profile is not None:
        params["traveller"] = profile["username"]
    elif user_id is not None:
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
    if owner:
        require_login()
    if not 1 <= flight_id <= SQLITE_MAX_INTEGER:
        abort(404)
    entry = flights.get_flight(flight_id)
    if entry is None:
        abort(404)
    if owner and entry["user_id"] != g.user["id"]:
        abort(403)
    return entry


@app.get("/my-flights")
def my_flights():
    """Show the signed-in traveller's history."""
    require_login()
    return flight_listing(g.user["id"])


@app.get("/travellers/<username>")
def traveller_profile(username):
    """Show a traveller's public diary and statistics."""
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        abort(404)
    profile = users.find_by_username(username)
    if profile is None:
        abort(404)
    return flight_listing(profile["id"], profile)


@app.get("/flights/<int:flight_id>")
def flight_detail(flight_id):
    """Show a flight to any visitor, preserving the originating history."""
    entry = find_flight(flight_id)
    mine = request.args.get("scope") == "mine"
    filters, _ = flights.search_filters(request.args)
    page = request.args.get("page", 1, type=int)
    params = filters | {"page": page if page > 1 else None, "_anchor": f"flight-{flight_id}"}
    if request.args.get("traveller", "").casefold() == entry["username"].casefold():
        back_url = url_for("traveller_profile", username=entry["username"], **params)
        back_label = entry["username"] + "’s flight history"
    else:
        back_url = url_for("my_flights" if mine else "index", **params)
        back_label = "My flights" if mine else "Public flights"
    return render_template("flight.html", flight=entry, rating_fields=reviews.RATING_FIELDS,
                           back_label=back_label, back_url=back_url)


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
    names = (flights.airport_names((values["departure_code"], values["arrival_code"]))
             if action != "route" else {})
    errors = flights.route_errors(values, names) if action != "route" else {}
    details = action != "route" and not errors
    cabins = flights.choices("cabin") if details else []
    purposes = flights.choices("purpose") if details else []
    if details and action == "save":
        errors = flights.detail_errors(values, cabins, purposes) | reviews.errors(values)
        if not errors:
            flight_id = flights.save(values, g.user["id"], entry["id"] if entry else None)
            return redirect(url_for("flight_detail", flight_id=flight_id))
    hidden_keys = flights.ROUTE_FIELDS if details else flights.DETAIL_FIELDS
    hidden_fields = {key: values[key] for key in hidden_keys}
    return render_template("flight_form.html", hidden_fields=hidden_fields, values=values,
                           errors=errors, names=names,
                           details=details, editing=entry is not None, cabins=cabins,
                           purposes=purposes, rating_fields=reviews.RATING_FIELDS,
                           today=date.today().isoformat(), picked=picked), (
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
