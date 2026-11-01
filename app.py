"""Flightbook's server-rendered web application."""

from datetime import timedelta
import os
import re
import secrets
import sqlite3

import click
from flask import Flask, abort, g, redirect, render_template, request, session, url_for

import db
import users

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
            abort(403, description="This form has expired. Reload the page and try again.")
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
    return render_template("index.html")


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
