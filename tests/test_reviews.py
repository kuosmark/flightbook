"""Flight review persistence, validation, and authorization integration tests."""

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from html_helpers import Page

from app import app
import db
import flights
import users


class ReviewsTest(unittest.TestCase):
    """Exercise reviews through the real flight form and isolated SQLite database."""

    def setUp(self):
        # unittest owns cleanup even when a test fails.
        # pylint: disable-next=consider-using-with
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(app.config, TESTING=True, SECRET_KEY="test-key",
                                     DATABASE=str(Path(directory) / "test.db")))
        with app.app_context():
            db.init_db()
            self.owner = users.create_user("Reviewer", "long test password")
            self.other = users.create_user("Other", "long test password")
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session.update(user_id=self.owner, csrf_token="token")
        self.values = dict.fromkeys(flights.FIELDS, "") | {
            "departure_date": "2025-01-15", "departure_code": "HEL", "arrival_code": "AMS",
            "overall_rating": "4", "seat_rating": "3", "service_rating": "5",
            "food_rating": "2", "entertainment_rating": "1", "wifi_rating": "",
            "review": "A pleasant flight.\nWould fly again."}

    def post(self, path="/flights/new", **changes):
        """Submit an authenticated draft through normal validation."""
        return self.client.post(path, data=self.values | {
            "csrf_token": "token", "action": "save"} | changes)

    def test_round_trip_and_clear(self):
        """Persist every rating, expose the review, then remove it independently."""
        response = self.post()
        self.assertEqual(response.status_code, 302)
        path = response.location
        page = self.client.get(path).get_data(as_text=True)
        self.assertIn("A pleasant flight.\nWould fly again.", page)
        self.assertIn("4 out of 5 stars", page)
        self.assertNotIn("Wi-Fi", page)
        edit = self.client.get(path + "/edit")
        for key, value in self.values.items():
            if key.endswith("_rating"):
                self.assertEqual(Page(edit).values[key], value)
        self.assertIn(self.values["review"], edit.get_data(as_text=True))
        for listing in ("/", "/my-flights"):
            self.assertIn(b"4 out of 5 stars", self.client.get(listing).data)
        cleared = {key: "" for key in self.values if key.endswith("_rating") or key == "review"}
        self.assertEqual(self.post(path + "/edit", **cleared).status_code, 302)
        with app.app_context():
            self.assertEqual(db.query("SELECT flight_id FROM flight_reviews"), [])
            self.assertIsNotNone(flights.get_flight(int(path.rsplit("/", 1)[1])))

    def test_invalid_ratings_and_review_length(self):
        """Reject forged scores and oversized text without creating a flight."""
        for key in ("overall_rating", "seat_rating", "service_rating", "food_rating",
                    "entertainment_rating", "wifi_rating"):
            for value in ("0", "6", "-1", "1.5", "abc", "１"):
                with self.subTest(field=key, value=value):
                    response = self.post(**{key: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(b"Select a rating from 1 to 5", response.data)
        self.assertEqual(self.post(review="x" * 5001).status_code, 400)
        with app.app_context():
            self.assertEqual(db.query("SELECT id FROM flights"), [])

    def test_unicode_limit_and_escaped_text(self):
        """Accept a long encoded form and render HTML as plain review text."""
        response = self.post(review="界" * 5000)
        self.assertEqual(response.status_code, 302)
        response = self.post(review='<script>alert("x")</script>\nSecond line')
        page = self.client.get(response.location).get_data(as_text=True)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('<script>alert', page)

    def test_browser_line_endings_at_character_limit(self):
        """Count textarea line breaks once, including browser form serialization."""
        review = "x" * 2499 + "\r\n" + "y" * 2500
        response = self.post(review=review)
        self.assertEqual(response.status_code, 302)
        edit = Page(self.client.get(response.location + "/edit"))
        self.assertEqual(edit.values["review"], review.replace("\r\n", "\n"))

    def test_draft_survives_route_picker_and_errors(self):
        """Changing route or fixing validation must not discard the review."""
        for changes in ({"action": "route"}, {"find": "departure_code", "q": "Helsinki"},
                        {"airline": "x" * 101}):
            response = self.post(**changes)
            page = response.get_data(as_text=True)
            self.assertIn("A pleasant flight.", page)
            self.assertEqual(Page(response).values["seat_rating"], "3")

    def test_picker_round_trip_saves_review(self):
        """Submit the actual preserved controls through airport selection and saving."""
        for action in ({"pick": "LHR"}, {"cancel_find": "1"}):
            with self.subTest(action=action):
                picker = self.post(find="departure_code", q="London")
                draft = Page(picker).values
                route = self.client.post("/flights/new", data=draft | action)
                draft = Page(route).values
                details = self.client.post("/flights/new", data=draft | {"action": "continue"})
                draft = Page(details).values
                saved = self.client.post("/flights/new", data=draft | {"action": "save"})
                self.assertEqual(saved.status_code, 302)
                edit = Page(self.client.get(saved.location + "/edit"))
                self.assertEqual(edit.values["review"], self.values["review"])
                self.assertEqual(edit.values["service_rating"], "5")
                self.assertEqual(edit.values["departure_code"], action.get("pick", "HEL"))

    def test_ownership_and_csrf(self):
        """Reject unauthorized changes to a flight's review."""
        path = self.post().location
        for user_id, expected in ((self.other, 403), (None, 401)):
            with self.client.session_transaction() as session:
                session.clear()
                session["csrf_token"] = "token"
                if user_id is not None:
                    session["user_id"] = user_id
            self.assertEqual(self.post(path + "/edit", review="Forged").status_code, expected)
        with self.client.session_transaction() as session:
            session["user_id"] = self.owner
        self.assertEqual(self.post(path + "/edit", csrf_token="bad").status_code, 403)
        self.assertIn(b"A pleasant flight.", self.client.get(path).data)

    def test_delete_removes_only_the_linked_review(self):
        """Delete a flight and its review while preserving another reviewed flight."""
        created = self.post()
        other = self.post(review="Keep this review.", overall_rating="2")
        self.assertEqual(created.status_code, 302)
        self.assertEqual(other.status_code, 302)
        path = created.location
        flight_id = int(path.rsplit("/", 1)[1])
        other_id = int(other.location.rsplit("/", 1)[1])
        with app.app_context():
            before = [dict(row) for row in db.query(
                "SELECT flight_id, overall_rating, review FROM flight_reviews ORDER BY flight_id")]
        self.assertEqual(before, [
            {"flight_id": flight_id, "overall_rating": 4, "review": self.values["review"]},
            {"flight_id": other_id, "overall_rating": 2, "review": "Keep this review."}])
        self.assertEqual(self.post(path + "/delete").status_code, 302)
        with app.app_context():
            self.assertIsNone(flights.get_flight(flight_id))
            self.assertIsNotNone(flights.get_flight(other_id))
            remaining = [dict(row) for row in db.query(
                "SELECT flight_id, overall_rating, review FROM flight_reviews")]
        self.assertEqual(remaining, [
            {"flight_id": other_id, "overall_rating": 2, "review": "Keep this review."}])

    def test_existing_database_upgrade_is_repeatable(self):
        """Adding the review table preserves pre-feature accounts and flights."""
        path = self.post().location
        with app.app_context():
            db.execute("DROP TABLE IF EXISTS flight_reviews")
            db.init_db()
            db.init_db()
            self.assertEqual(len(db.query("SELECT id FROM flights")), 1)
            self.assertEqual(len(db.query("SELECT id FROM users")), 2)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.post(path + "/edit").status_code, 302)
        self.assertIn(b"A pleasant flight.", self.client.get(path).data)

    def test_review_failure_rolls_back_flight_changes(self):
        """A failed review write must not leave a partially updated flight."""
        path = self.post().location
        with app.app_context():
            db.execute("""CREATE TRIGGER reject_review BEFORE UPDATE ON flight_reviews
                BEGIN SELECT RAISE(ABORT, 'test review failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.post(path + "/edit", airline="Should roll back", review="Changed")
        page = self.client.get(path).get_data(as_text=True)
        self.assertNotIn("Should roll back", page)
        self.assertIn("A pleasant flight.", page)
