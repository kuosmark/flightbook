"""SQLite connections and schema initialization."""

import sqlite3

from flask import current_app, g


def get_connection():
    """Reuse one connection for the current application context."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_connection(_error=None):
    """Close the connection at the end of the application context."""
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    """Create missing tables without deleting existing accounts."""
    with current_app.open_resource("schema.sql") as schema:
        get_connection().executescript(schema.read().decode("utf-8"))


def query(sql, parameters=()):
    """Return rows from a parameterized query."""
    return get_connection().execute(sql, parameters).fetchall()


def execute(sql, parameters=()):
    """Commit a write and return the inserted row ID."""
    connection = get_connection()
    with connection:
        cursor = connection.execute(sql, parameters)
    return cursor.lastrowid
