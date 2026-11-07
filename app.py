"""Flightbook's server-rendered web application."""

from datetime import date, timedelta
import os
import re
import secrets
import sqlite3

import click
from flask import Flask, abort, g, redirect, render_template, request, session, url_for

import db
import users
import flights

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLIGHTBOOK_SECRET_KEY"),
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
    """Create the application's database tables."""
    db.init_db()
    click.echo("Database initialized.")


@app.before_request
def load_session():
    """Load the current account and protect state-changing requests."""
    if not app.secret_key:
        raise RuntimeError("Set FLIGHTBOOK_SECRET_KEY before running Flightbook.")
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


def flight_listing(user_id=None):
    """Render either recent public entries or the current user's flight history."""
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        abort(404)
    if not 1 <= page <= 1000000:
        abort(404)
    entries = flights.list_flights(page, user_id)
    if page > 1 and not entries:
        abort(404)
    return render_template("index.html", entries=entries[:flights.PAGE_SIZE], page=page,
                           has_next=len(entries) > flights.PAGE_SIZE, mine=user_id is not None)


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
    return render_template("flight.html", flight=find_flight(flight_id))


def airport_picker(data, values, field_labels):
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
                           values=values, query=query, searched="q" in data,
                           matches=matches[:flights.AIRPORT_RESULT_LIMIT],
                           more=len(matches) > flights.AIRPORT_RESULT_LIMIT), {}


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
