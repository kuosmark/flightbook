"""Public traveller profiles, statistics, and history navigation."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from html_helpers import Page
from app import app
import db
import flights
import users


class ProfilesTest(unittest.TestCase):
    """Use real queries and requests against an isolated diary."""

    def setUp(self):
        # unittest owns the temporary database and configuration cleanup.
        # pylint: disable-next=consider-using-with
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(app.config, TESTING=True, SECRET_KEY="profile-tests",
                                     DATABASE=str(Path(directory) / "test.db")))
        with app.app_context():
            db.init_db()
            self.owner = users.create_user("Traveller", "a long test password")
            self.other = users.create_user("OtherTraveller", "a long test password")
        self.client = app.test_client()
        self.values = dict.fromkeys(flights.FIELDS, "") | {
            "departure_date": "2025-01-01", "departure_code": "HEL", "arrival_code": "AMS"}
        self.path = "/travellers/Traveller"

    def add(self, user_id=None, **changes):
        """Insert a fixture without submitting a browser form."""
        with app.app_context():
            return flights.save(self.values | changes, user_id or self.owner)

    def test_public_profile_and_links(self):
        """Guests can reach a traveller from their flight and public listing."""
        flight_id = self.add()
        for path in ("/", f"/flights/{flight_id}"):
            self.assertIn(self.path, Page(self.client.get(path)).links)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Traveller", response.data)
        self.assertIn(b"Flight history", response.data)
        self.assertNotIn(f"/flights/{flight_id}/edit", Page(response).links)
        self.assertEqual(self.client.get("/travellers/traveller").status_code, 200)
        for username in ("Missing", "x" * 100, "1234567890123456789012345678901234567890"):
            self.assertEqual(self.client.get("/travellers/" + username).status_code, 404)

    def test_statistics_count_flights_airports_and_rated_sample(self):
        """Count each airport once per flight and omit unrated flights from the mean."""
        year = date.today().year
        self.add(departure_date=f"{year}-01-01", overall_rating="5")
        self.add(departure_date=f"{year - 1}-12-31", departure_code="AMS",
                 arrival_code="HEL", overall_rating="3")
        self.add(departure_date=f"{year}-01-02", arrival_code="HEL", seat_rating="1")
        self.add(departure_code="LHR", arrival_code="CDG")
        self.add(self.other, overall_rating="1", departure_code="JFK")
        with app.app_context():
            summary = flights.rating_statistics(self.owner)
            self.assertEqual(flights.count_flights({}, self.owner), 4)
            self.assertEqual(flights.flights_in_year(self.owner, year), 2)
            self.assertEqual(dict(summary), {"average_rating": 4.0, "rated_flights": 2})
            self.assertEqual(flights.airport_count(self.owner), 4)
            airports = flights.top_airports(self.owner)
        self.assertEqual([(row["code"], row["total"]) for row in airports],
                         [("HEL", 3), ("AMS", 2), ("CDG", 1)])
        response = self.client.get(self.path)
        self.assertIn(b"4.0 / 5", response.data)
        self.assertIn(b"2 rated flights", response.data)
        filtered = self.client.get(self.path + "?from=LHR")
        self.assertIn(b"4.0 / 5", filtered.data)
        self.assertIn(b"2 rated flights", filtered.data)

    def test_yearly_count_boundaries_and_empty_statistics(self):
        """Include both ends of the selected year, excluding adjacent years and users."""
        with app.app_context():
            self.assertEqual(flights.count_flights({}, self.owner), 0)
            self.assertEqual(flights.flights_in_year(self.owner, 2026), 0)
            self.assertEqual(dict(flights.rating_statistics(self.owner)),
                             {"average_rating": None, "rated_flights": 0})
        for departure_date in ("2025-12-31", "2026-01-01", "2026-12-31", "2027-01-01"):
            self.add(departure_date=departure_date)
        self.add(self.other, departure_date="2026-06-01")
        with app.app_context():
            self.assertEqual(flights.count_flights({}, self.owner), 4)
            self.assertEqual(flights.flights_in_year(self.owner, 2026), 2)

    def test_statistics_update_after_edit_and_delete(self):
        """Profile totals reflect the saved diary rather than cached counters."""
        flight_id = self.add(overall_rating="5")
        with app.app_context():
            flights.save(self.values | {"arrival_code": "LHR", "overall_rating": "2"},
                         self.owner, flight_id)
            self.assertEqual(flights.rating_statistics(self.owner)
                             ["average_rating"], 2.0)
            self.assertEqual({row["code"] for row in flights.top_airports(self.owner)},
                             {"HEL", "LHR"})
            flights.delete(flight_id, self.owner)
            self.assertEqual(flights.count_flights({}, self.owner), 0)
            self.assertEqual(flights.airport_count(self.owner), 0)
            self.assertEqual(flights.top_airports(self.owner), [])

    def test_empty_and_unrated_profiles(self):
        """An empty diary and unrated flights do not show an invented rating."""
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No flights yet", response.data)
        self.assertIn(b"Not rated", response.data)
        self.assertNotIn(b"Filter flights", response.data)
        self.assertNotIn(b"Log in to add a flight", response.data)
        self.add()
        self.assertIn(b"Not rated", self.client.get(self.path).data)
        with app.app_context():
            summary = flights.rating_statistics(self.owner)
            self.assertIsNone(summary["average_rating"])
            self.assertEqual(summary["rated_flights"], 0)

    def test_history_scope_pagination_filters_and_back_link(self):
        """Every history link keeps the selected traveller and applied filters."""
        ids = [self.add(airline="Finnair") for _ in range(21)]
        other_id = self.add(self.other, airline="Finnair")
        self.add(arrival_code="LHR", airline="Other airline")
        response = self.client.get(self.path + "?airline=Finnair")
        links = Page(response).links
        next_page = next(link for link in links if "page=2" in link)
        self.assertTrue(next_page.startswith(self.path + "?"))
        response = self.client.get(next_page)
        links = Page(response).links
        detail = next(link for link in links if link.startswith(f"/flights/{ids[0]}?"))
        self.assertNotIn(f"/flights/{other_id}?", response.get_data(as_text=True))
        self.assertEqual(parse_qs(urlparse(detail).query)["traveller"], ["Traveller"])
        back = next(link for link in Page(self.client.get(detail)).links
                    if link.startswith(self.path + "?"))
        self.assertEqual(parse_qs(urlparse(back).query), {"page": ["2"], "airline": ["Finnair"]})
        self.assertEqual(self.client.get(back).status_code, 200)
        no_matches = self.client.get(self.path + "?airline=Missing")
        self.assertIn(b"No flights match these filters", no_matches.data)
        self.assertIn(b"Filter flights", no_matches.data)
        self.assertIn(self.path, Page(no_matches).links)
        self.assertEqual(self.client.get(self.path + "?from=INVALID").status_code, 400)
        self.assertEqual(self.client.get(self.path + "?page=999").status_code, 404)

    def test_history_orders_departure_dates_before_entry_ids(self):
        """Later additions of older flights must not lead the profile history."""
        newer = self.add(departure_date="2025-02-01")
        older = self.add(departure_date="2025-01-01")
        tied = self.add(departure_date="2025-02-01")
        links = [urlparse(link).path for link in Page(self.client.get(self.path)).links
                 if link.startswith("/flights/")]
        self.assertEqual(links, [f"/flights/{tied}", f"/flights/{newer}", f"/flights/{older}"])

    def test_picker_preserves_profile_scope(self):
        """Selecting an airport returns to the same traveller's history."""
        self.add()
        picker = self.client.get(self.path, query_string={"find": "from", "q": "London"})
        self.assertEqual(picker.status_code, 200)
        values = Page(picker).values | {"pick": "LHR"}
        response = self.client.get(self.path, query_string=values)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.startswith(self.path + "?"))
        returned = self.client.get(response.location)
        self.assertEqual(Page(returned).values["from"], "LHR")
        self.assertIn(b"Traveller", returned.data)

    def test_own_profile_navigation_does_not_grant_other_users_access(self):
        """Profile visibility does not change permissions on flight management."""
        flight_id = self.add()
        with self.client.session_transaction() as session:
            session.update(user_id=self.other, csrf_token="token")
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Add flight", response.data)
        self.assertIn("/travellers/OtherTraveller", Page(response).links)
        for action in ("edit", "delete"):
            response = self.client.post(f"/flights/{flight_id}/{action}", data={
                "csrf_token": "token", "action": "save"})
            self.assertEqual(response.status_code, 403)
        with self.client.session_transaction() as session:
            session["user_id"] = self.owner
        self.assertIn(b"Add flight", self.client.get(self.path).data)
