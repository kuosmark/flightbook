"""Flight CRUD, ownership, reference data, and pagination integration tests."""

from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import app
import db
import flights
import users


class FlightsTest(unittest.TestCase):
    """Exercise flight requests against an isolated database."""

    def setUp(self):
        # unittest owns cleanup even if setup or an assertion fails.
        # pylint: disable-next=consider-using-with
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(app.config, TESTING=True, SECRET_KEY="test-only",
                                     DATABASE=str(Path(directory) / "test.db")))
        with app.app_context():
            db.init_db()
            self.owner = users.create_user("Traveller", "a long test password")
            self.other = users.create_user("Another", "a long test password")
        self.client = app.test_client()
        self.sign_in(self.owner)
        self.values = dict.fromkeys(flights.FIELDS, "")
        self.values.update(departure_date="2025-01-15", departure_code="HEL", arrival_code="AMS")

    def sign_in(self, user_id):
        """Choose a test account without bypassing request authorization."""
        with self.client.session_transaction() as browser_session:
            browser_session.clear()
            if user_id is not None:
                browser_session["user_id"] = user_id
            browser_session["csrf_token"] = "test-token"

    def post(self, path, values=None):
        """Submit a CSRF-protected form."""
        return self.client.post(path, data={"csrf_token": "test-token", **(values or {})})

    def create(self, **changes):
        """Create an entry and return its detail URL."""
        response = self.post("/flights/new", self.values | changes)
        self.assertEqual(response.status_code, 302)
        return response.location

    def test_create_edit_delete_and_public_visibility(self):
        """Round-trip all fields, preserve ownership, and confirm before deletion."""
        path = self.create(departure_code=" hel ", arrival_code="ams", airline="Finnair",
                           flight_number="ay123", aircraft="Airbus A350", seat="12a",
                           cabin_id="3", purpose_id="7", user_id=str(self.other))
        page = self.client.get(path).get_data(as_text=True)
        for text in ("Helsinki Vantaa Airport", "Amsterdam Airport Schiphol", "AY123", "12A",
                     "Finnair", "Business", "Other", "Traveller"):
            self.assertIn(text, page)
        guest = app.test_client()
        self.assertEqual(guest.get(path).status_code, 200)
        self.assertIn(path, guest.get("/").get_data(as_text=True))
        self.assertNotIn("Edit flight", guest.get(path).get_data(as_text=True))
        response = self.post(path + "/edit", self.values | {"airline": "Updated airline"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("Updated airline", self.client.get(path).get_data(as_text=True))
        self.assertEqual(self.client.get(path + "/delete").status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.post(path + "/delete").status_code, 302)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_other_users_and_guests_cannot_modify_entries(self):
        """Reject direct URLs and forged POSTs, not just hide controls."""
        path = self.create()
        for user_id, status in ((self.other, 403), (None, 401)):
            self.sign_in(user_id)
            for action in ("edit", "delete"):
                self.assertEqual(self.client.get(path + "/" + action).status_code, status)
                self.assertEqual(self.post(path + "/" + action, self.values).status_code, status)
        self.assertEqual(self.post("/flights/new", self.values).status_code, 401)
        self.assertEqual(self.client.get("/my-flights").status_code, 401)
        self.assertEqual(self.client.get(path).status_code, 200)

    def test_write_requests_require_csrf(self):
        """No flight mutation accepts missing or incorrect tokens."""
        path = self.create()
        for target in ("/flights/new", path + "/edit", path + "/delete"):
            for token in ("", "wrong"):
                response = self.client.post(target, data=self.values | {"csrf_token": token})
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(path).status_code, 200)

    def test_invalid_fields_preserve_form_and_do_not_write(self):
        """Validate real dates, strict codes, lengths, and category types."""
        cases = [
            ("departure_date", "2025-02-30"), ("departure_date", "20250115"),
            ("departure_date", (date.today() + timedelta(days=1)).isoformat()),
            ("departure_code", "HÉL"), ("arrival_code", "AM"), ("departure_code", ""),
            ("flight_number", "ay 1 23"), ("flight_number", "AY 123"),
            ("flight_number", "1234"), ("flight_number", "AY12345"),
            ("seat", "0A"), ("seat", "12 AB"), ("seat", "1000A"),
            ("airline", "a" * 101), ("aircraft", "a" * 101),
            ("cabin_id", "5"), ("purpose_id", "1"), ("purpose_id", "999"),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                response = self.post("/flights/new", self.values | {field: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn('role="alert"', response.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS count FROM flights")[0]["count"], 0)

    def test_unknown_codes_and_escaped_text(self):
        """Unknown valid codes survive lookup joins and user text is escaped."""
        path = self.create(departure_code="ZZZ", airline="<script>alert(1)</script>",
                           flight_number="U2123A", seat="999Z")
        page = self.client.get(path).get_data(as_text=True)
        self.assertIn("ZZZ", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertIn("ZZZ", self.client.get("/").get_data(as_text=True))

    def test_import_is_repeatable_and_preserves_flights(self):
        """Real snapshot imports safely without overwriting accounts or flights."""
        path = self.create()
        with app.app_context():
            db.init_db()
            count = db.query("SELECT COUNT(*) AS count FROM airports")[0]["count"]
            self.assertEqual(count, 9052)
            self.assertEqual(len(flights.choices("cabin")), 4)
            self.assertEqual(len(flights.choices("purpose")), 3)
        self.assertEqual(self.client.get(path).status_code, 200)
        page = self.client.get("/flights/new").get_data(as_text=True)
        self.assertIn("Search airports", page)
        self.assertNotIn("<datalist", page)

    def test_pagination_and_personal_order(self):
        """Public feed orders additions; personal history orders flight dates."""
        with app.app_context():
            for number in range(21):
                flights.save(self.values | {"airline": f"Carrier-{number:02d}"}, self.owner)
            flights.save(self.values | {"departure_date": "2020-01-01", "airline": "Older flight"},
                         self.owner)
            flights.save(self.values | {"airline": "Other person's flight"}, self.other)
        public = self.client.get("/").get_data(as_text=True)
        self.assertIn("Other person", public)
        self.assertNotIn("Carrier-00", public)
        second = self.client.get("/?page=2").get_data(as_text=True)
        self.assertIn("Carrier-00", second)
        personal = self.client.get("/my-flights").get_data(as_text=True)
        self.assertNotIn("Other person", personal)
        self.assertNotIn("Older flight", personal)
        self.assertIn("Older flight", self.client.get("/my-flights?page=2").get_data(as_text=True))
        for page in ("0", "-1", "abc", "100000000000000000", "3"):
            self.assertEqual(self.client.get("/?page=" + page).status_code, 404)

    def test_airport_lookup_preserves_form_without_saving(self):
        """Searching and selecting bypass flight validation and preserve unsaved fields."""
        values = self.values | {"departure_date": "", "departure_code": "he",
                                "airline": "Unsaved airline", "arrival_code": "AMS"}
        response = self.post("/flights/new", values | {"airport_search": "departure_code"})
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Helsinki Vantaa Airport", page)
        self.assertIn('value="Unsaved airline"', page)
        selected = self.post("/flights/new", values | {"airport_choice": "departure_code:HEL"})
        self.assertEqual(selected.status_code, 200)
        self.assertIn('value="HEL"', selected.get_data(as_text=True))
        self.assertIn('value="AMS"', selected.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS count FROM flights")[0]["count"], 0)
        path = self.create()
        response = self.post(path + "/edit", values | {"airport_search": "arrival_code"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Unsaved airline", self.client.get(path).get_data(as_text=True))
        self.assertEqual(self.post(path + "/edit", {"airport_search": "invalid"}).status_code, 400)

    def test_airport_search_matches_only_code_prefixes(self):
        """Full codes return one result; names and malformed queries never match."""
        with app.app_context():
            self.assertEqual([row["iata_code"] for row in flights.search_airports(" ams ")],
                             ["AMS"])
            matches = flights.search_airports("he")
            self.assertTrue(matches)
            self.assertTrue(all(row["iata_code"].startswith("HE") for row in matches))
            for query in ("Helsinki", "%_", "", "123", "A1", "Ä", "AMSS"):
                self.assertEqual(flights.search_airports(query), [])
            self.assertLessEqual(len(flights.search_airports("a")), 21)

    def test_missing_flight_returns_not_found(self):
        """Missing entries have consistent status on view, edit, and delete."""
        for suffix in ("", "/edit", "/delete"):
            self.assertEqual(self.client.get("/flights/999" + suffix).status_code, 404)
