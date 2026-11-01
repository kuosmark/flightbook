"""Account flows against an isolated SQLite database."""

from datetime import timedelta
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash

from app import app
import db
import users


class AccountsTest(unittest.TestCase):
    """Exercise real routes, sessions, queries, and password hashes."""

    password = "a long test passphrase"

    def setUp(self):
        # unittest closes this context after each test, including on failure.
        # pylint: disable-next=consider-using-with
        self.directory = self.enterContext(TemporaryDirectory())
        configuration = patch.dict(
            app.config,
            TESTING=True,
            SECRET_KEY="test-only-secret",
            DATABASE=str(Path(self.directory) / "test.db"),
        )
        self.enterContext(configuration)
        with app.app_context():
            db.init_db()
        self.client = app.test_client()

    def post_form(self, path, data=None):
        """Send a form with the token issued to this browser."""
        self.client.get("/login")
        with self.client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        return self.client.post(path, data={"csrf_token": token, **(data or {})})

    def register(self, username="Markus", password=None, confirmation=None):
        """Register with valid defaults unless a test overrides them."""
        password = self.password if password is None else password
        confirmation = password if confirmation is None else confirmation
        return self.post_form("/register", {
            "username": username,
            "password": password,
            "confirmation": confirmation,
        })

    def test_registration_hashes_password_and_signs_in(self):
        """Store the chosen spelling and a verifiable hash, never plaintext."""
        response = self.register(" Markus ")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")
        with app.app_context():
            account = db.query("SELECT id, username, password_hash FROM users")[0]
        self.assertEqual(account["username"], "Markus")
        self.assertNotEqual(account["password_hash"], self.password)
        self.assertTrue(check_password_hash(account["password_hash"], self.password))
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session["user_id"], account["id"])
            self.assertTrue(browser_session.permanent)
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('class="account-name">Markus</span>', page)
        self.assertIn("Log out", page)

    def test_case_insensitive_uniqueness_is_enforced_by_database(self):
        """Both direct inserts and registration reject a case-only duplicate."""
        self.register()
        with app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                users.create_user("markus", self.password)
        self.post_form("/logout")
        response = self.register("MARKUS")
        self.assertEqual(response.status_code, 400)
        self.assertIn("already taken", response.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS count FROM users")[0]["count"], 1)

    def test_login_accepts_other_capitalization_and_logout_clears_session(self):
        """A user can return using another capitalization, then sign out."""
        self.register()
        self.post_form("/logout")
        response = self.post_form("/login", {
            "username": " mARKUS ", "password": self.password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("Markus", self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.post_form("/logout").status_code, 302)
        with self.client.session_transaction() as browser_session:
            self.assertNotIn("user_id", browser_session)
        self.assertNotIn("Log out", self.client.get("/").get_data(as_text=True))

    def test_invalid_registration_does_not_create_accounts(self):
        """Check missing fields, boundaries, character rules, and confirmation."""
        cases = [
            ("", self.password, self.password),
            ("ab", self.password, self.password),
            ("a" * 31, self.password, self.password),
            ("Mäki", self.password, self.password),
            ("two names", self.password, self.password),
            ("<script>alert(1)</script>", self.password, self.password),
            ("Markus", "", ""),
            ("Markus", "a" * 14, "a" * 14),
            ("Markus", "a" * 129, "a" * 129),
            ("Markus", "🌍" * 129, "🌍" * 129),
            ("Markus", self.password, "different password"),
        ]
        for username, password, confirmation in cases:
            with self.subTest(username=username, password_length=len(password)):
                response = self.register(username, password, confirmation)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("<script>", response.get_data(as_text=True))
                self.assertNotIn(f'value="{self.password}"', response.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS count FROM users")[0]["count"], 0)
        response = self.post_form("/register")
        self.assertEqual(response.status_code, 400)

    def test_registration_accepts_boundaries(self):
        """Accept both ends of the documented lengths, including spaces in passwords."""
        for username, password in [("Ab_", "a " + "b" * 13), ("Z" * 30, "p" * 128)]:
            with self.subTest(username=username):
                self.assertEqual(self.register(username, password).status_code, 302)
                self.post_form("/logout")

    def test_unicode_password_is_preserved_in_full(self):
        """Count Unicode code points and verify the entire password at login."""
        password = "🌍" * 128
        self.assertEqual(self.register(password=password).status_code, 302)
        self.post_form("/logout")
        truncated = self.post_form("/login", {"username": "Markus", "password": password[:64]})
        self.assertEqual(truncated.status_code, 400)
        complete = self.post_form("/login", {"username": "Markus", "password": password})
        self.assertEqual(complete.status_code, 302)

    def test_failed_login_uses_same_message_and_preserves_username(self):
        """Invalid credentials cannot authenticate or reveal which field failed."""
        self.register()
        self.post_form("/logout")
        for username, password in [
            ("Markus", self.password.upper()),
            ("Unknown", self.password),
            ("' OR 1=1 --", self.password),
            ("Markus", "p" * 129),
            ("", ""),
        ]:
            with self.subTest(username=username):
                response = self.post_form("/login", {"username": username, "password": password})
                self.assertEqual(response.status_code, 400)
                self.assertIn("Incorrect username or password.", response.get_data(as_text=True))
                with self.client.session_transaction() as browser_session:
                    self.assertNotIn("user_id", browser_session)
        response = self.post_form("/login", {"username": "Markus", "password": "wrong"})
        self.assertIn('value="Markus"', response.get_data(as_text=True))

    def test_all_forms_reject_invalid_csrf(self):
        """Registration, login, and logout require the browser's own token."""
        for path in ("/register", "/login", "/logout"):
            for token in (None, "wrong", "ä"):
                with self.subTest(path=path, token=token):
                    self.client.get("/login")
                    data = {} if token is None else {"csrf_token": token}
                    self.assertEqual(self.client.post(path, data=data).status_code, 403)
        self.register()
        self.assertEqual(self.client.post("/logout").status_code, 403)
        with self.client.session_transaction() as browser_session:
            self.assertIn("user_id", browser_session)

    def test_login_replaces_old_session_and_token(self):
        """Successful authentication rotates CSRF and discards anonymous session data."""
        self.client.get("/login")
        with self.client.session_transaction() as browser_session:
            old_token = browser_session["csrf_token"]
            browser_session["unrelated"] = "old data"
        self.register()
        with self.client.session_transaction() as browser_session:
            self.assertNotEqual(browser_session["csrf_token"], old_token)
            self.assertNotIn("unrelated", browser_session)
        response = self.client.post("/logout", data={"csrf_token": old_token})
        self.assertEqual(response.status_code, 403)

    def test_session_renews_and_expires_after_seven_inactive_days(self):
        """Active browsing renews the cookie; seven idle days invalidate it."""
        now = int(time.time())
        day = 24 * 60 * 60
        self.assertEqual(app.permanent_session_lifetime, timedelta(days=7))
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=now):
            self.register()
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=now + 6 * day):
            response = self.client.get("/")
            self.assertIn("Log out", response.get_data(as_text=True))
            cookie = response.headers["Set-Cookie"]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Lax", cookie)
            self.assertIn("Expires=", cookie)
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=now + 12 * day):
            self.assertIn("Log out", self.client.get("/").get_data(as_text=True))
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=now + 20 * day):
            self.assertNotIn("Log out", self.client.get("/").get_data(as_text=True))

    def test_tampered_cookie_is_rejected(self):
        """Changing a signed cookie cannot create an authenticated session."""
        self.register()
        cookie_name = app.config["SESSION_COOKIE_NAME"]
        cookie = self.client.get_cookie(cookie_name).value
        payload, timestamp, signature = cookie.rsplit(".", 2)
        changed = ("A" if signature[0] != "A" else "B") + signature[1:]
        self.client.set_cookie(cookie_name, f"{payload}.{timestamp}.{changed}")
        self.assertNotIn("Log out", self.client.get("/").get_data(as_text=True))

    def test_signed_in_users_skip_account_forms(self):
        """Existing sessions return to the homepage instead of creating another account."""
        self.register()
        for path in ("/login", "/register"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, "/")

    def test_initialization_preserves_existing_accounts(self):
        """Repeating setup is safe for an existing database."""
        self.register()
        result = app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0)
        with app.app_context():
            self.assertEqual(db.query("SELECT username FROM users")[0]["username"], "Markus")

    def test_missing_secret_has_clear_error(self):
        """Do not silently run account forms without a signing key."""
        with patch.dict(app.config, SECRET_KEY=None):
            with self.assertRaisesRegex(RuntimeError, "Set FLIGHTBOOK_SECRET_KEY"):
                self.client.get("/login")
