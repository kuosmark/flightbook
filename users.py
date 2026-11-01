"""Account storage and password verification."""

from werkzeug.security import check_password_hash, generate_password_hash

import db


def create_user(username, password):
    """Store an account with a salted password hash."""
    return db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )


def authenticate(username, password):
    """Return the account ID if the supplied credentials match."""
    rows = db.query("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    if not rows or not check_password_hash(rows[0]["password_hash"], password):
        return None
    return rows[0]["id"]


def get_user(user_id):
    """Find an account by its stable ID."""
    rows = db.query("SELECT id, username FROM users WHERE id = ?", (user_id,))
    return rows[0] if rows else None
