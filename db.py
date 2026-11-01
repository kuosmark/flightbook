"""SQLite connections and schema initialization."""

import csv
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
    """Create missing tables and load the airport snapshot without deleting user data."""
    with current_app.open_resource("schema.sql") as schema:
        get_connection().executescript(schema.read().decode("utf-8"))

    with open(current_app.root_path + "/data/airports.csv", encoding="utf-8", newline="") as source:
        rows = csv.DictReader(source)
        with get_connection() as connection:
            connection.executemany(
                """INSERT INTO airports (id, iata_code, name, municipality, iso_country)
                   VALUES (:id, :iata_code, :name, :municipality, :iso_country)
                   ON CONFLICT(id) DO UPDATE SET iata_code = excluded.iata_code,
                   name = excluded.name, municipality = excluded.municipality,
                   iso_country = excluded.iso_country""", rows)


def query(sql, parameters=()):
    """Return rows from a parameterized query."""
    return get_connection().execute(sql, parameters).fetchall()


def execute(sql, parameters=()):
    """Commit a write and return the inserted row ID."""
    connection = get_connection()
    with connection:
        cursor = connection.execute(sql, parameters)
    return cursor.lastrowid
