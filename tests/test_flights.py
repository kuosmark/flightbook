"""Flight CRUD, ownership, reference data, and pagination integration tests."""

from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from html_helpers import Page, csrf_token

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

    def _submit_rendered_form(self, path, values=None):
        """Submit the token actually rendered in an accessible flight form."""
        response = self.client.get(path)
        token = csrf_token(response)
        return self.client.post(path, data={"csrf_token": token, **(values or {})})

    def create(self, **changes):
        """Create an entry and return its detail URL."""
        values = self.values | changes
        preview = self._submit_rendered_form("/flights/new", values | {"action": "continue"})
        self.assertEqual(preview.status_code, 200)
        self.assertIn(b"Change route or date", preview.data)
        response = self.client.post("/flights/new", data=values | {
            "action": "save", "csrf_token": csrf_token(preview),
            "confirm_departure_code": values["departure_code"],
            "confirm_arrival_code": values["arrival_code"]})
        self.assertEqual(response.status_code, 302)
        return response.location

    def test_create_edit_delete_and_public_visibility(self):
        """Round-trip all fields, preserve ownership, and confirm before deletion."""
        path = self.create(departure_code=" hel ", arrival_code="ams", airline="Finnair",
                           flight_number="ay123", aircraft="Airbus A350", seat="12a",
                           cabin_id="3", purpose_id="7", user_id=str(self.other))
        page = self.client.get(path).get_data(as_text=True)
        for text in ("Helsinki Vantaa Airport", "Amsterdam Airport Schiphol", "AY123", "12A",
                     "Finnair", "Business", "Other", "Traveller", "Airbus A350", "2025-01-15"):
            self.assertIn(text, page)
        edit_values = Page(self.client.get(path + "/edit")).values
        expected = self.values | {"airline": "Finnair", "flight_number": "AY123",
                                  "aircraft": "Airbus A350", "seat": "12A",
                                  "cabin_id": "3", "purpose_id": "7"}
        self.assertEqual({field: edit_values.get(field) for field in flights.FIELDS}, expected)
        guest = app.test_client()
        self.assertEqual(guest.get(path).status_code, 200)
        self.assertIn(path, guest.get("/").get_data(as_text=True))
        self.assertNotIn("Edit flight", guest.get(path).get_data(as_text=True))
        response = self._submit_rendered_form(
            path + "/edit", self.values | {"airline": "Updated airline", "action": "save"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("Updated airline", self.client.get(path).get_data(as_text=True))
        self.assertEqual(self.client.get(path + "/delete").status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self._submit_rendered_form(path + "/delete").status_code, 302)
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

    def test_invalid_fields_do_not_create_flights(self):
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
                response = self.post("/flights/new", self.values | {field: value, "action": "save"})
                self.assertEqual(response.status_code, 400)
                self.assertIn('role="alert"', response.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS count FROM flights")[0]["count"], 0)

    def test_invalid_create_and_edit_preserve_values(self):
        """Errors retain entered text and choices without inserting or updating a flight."""
        path = self.create(airline="Original airline")
        with app.app_context():
            original = dict(flights.get_flight(int(path.rsplit("/", 1)[1])))
        values = self.values | {"departure_date": "2024-03-12", "departure_code": "LHR",
                                "airline": "Unsaved & airline", "aircraft": "Airbus A321",
                                "flight_number": "AY 123", "seat": "14C",
                                "cabin_id": "3", "purpose_id": "7"}
        for target in ("/flights/new", path + "/edit"):
            with self.subTest(target=target):
                response = self._submit_rendered_form(target, values | {"action": "save"})
                self.assertEqual(response.status_code, 400)
                self.assertIn('role="alert"', response.get_data(as_text=True))
                rendered = Page(response).values
                self.assertEqual({field: rendered.get(field) for field in flights.FIELDS}, values)
                with app.app_context():
                    self.assertEqual(dict(flights.get_flight(original["id"])), original)
                    count = db.query("SELECT COUNT(*) AS count FROM flights")[0]["count"]
                    self.assertEqual(count, 1)

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
        self.assertIn("Find airport", page)
        self.assertNotIn("<datalist", page)

    def test_pagination_and_personal_order(self):
        """Public feed orders additions; personal history orders flight dates."""
        with app.app_context():
            ids = [flights.save(self.values | {"airline": f"Carrier-{number:02d}"}, self.owner)
                   for number in range(21)]
            older = flights.save(self.values | {"departure_date": "2020-01-01"}, self.owner)
            other = flights.save(self.values, self.other)
        histories = {
            "/": [other, older, *reversed(ids)],
            "/my-flights": [*reversed(ids), older],
        }
        for route, expected in histories.items():
            seen = []
            for page_number, expected_ids in ((1, expected[:20]), (2, expected[20:])):
                with self.subTest(route=route, page=page_number):
                    response = self.client.get(f"{route}?page={page_number}")
                    self.assertEqual(response.status_code, 200)
                    links = Page(response).links
                    entries = [link for link in links if link.startswith("/flights/")
                               and link.rsplit("/", 1)[1].isdigit()]
                    self.assertEqual(entries, [f"/flights/{entry}" for entry in expected_ids])
                    seen.extend(entries)
                    if page_number == 1:
                        self.assertIn(f"{route}?page=2", links)
                        self.assertNotIn(f"{route}?page=1", links)
                    else:
                        self.assertIn(f"{route}?page=1", links)
                        self.assertNotIn(f"{route}?page=3", links)
            self.assertEqual(seen, [f"/flights/{entry}" for entry in expected])
        for page in ("0", "-1", "abc", "100000000000000000", "3"):
            self.assertEqual(self.client.get("/?page=" + page).status_code, 404)

    def test_route_review_keeps_draft_without_writing(self):
        """Find, choose, continue, and change route never write or discard entered details."""
        path = "/flights/new"
        draft = self.values | {"departure_date": "", "airline": "Unsaved & Co"}
        lookup = draft | {"find": "departure_code", "q": "London"}
        cancelled = self.post(path, lookup | {"cancel_find": "1"})
        self.assertEqual(Page(cancelled).values["departure_code"], "HEL")
        self.assertNotIn(b"Helsinki Vantaa Airport", cancelled.data)
        options = self.post(path, lookup)
        self.assertIn(b"London Heathrow Airport (LHR)", options.data)
        self.assertIn(b"London Gatwick Airport (LGW)", options.data)
        selection = self.post(path, lookup | {"pick": "LHR"})
        self.assertIn("LHR — London Heathrow Airport", selection.get_data(as_text=True))
        values = Page(selection).values
        self.assertEqual(values["departure_code"], "LHR")
        self.assertEqual(values["airline"], "Unsaved & Co")
        values.update(departure_date="2025-04-03", action="continue")
        preview = self.post(path, values)
        self.assertIn(b"London Heathrow Airport (LHR)", preview.data)
        self.assertIn(b"Amsterdam Airport Schiphol (AMS)", preview.data)
        self.assertIn(b'<time datetime="2025-04-03">2025-04-03</time>', preview.data)
        back = self.post(path, values | {"action": "route", "seat": "12A"})
        self.assertEqual(Page(back).values["seat"], "12A")
        changed = self.post(path, Page(back).values | {"arrival_code": "HEL", "action": "continue"})
        self.assertIn(b"Helsinki Vantaa Airport (HEL)", changed.data)
        self.assertIn(b"London Heathrow Airport (LHR)", changed.data)
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM flights")[0]["n"], 0)

    def test_unlisted_airport_needs_confirmation_for_that_code(self):
        """Do not save an unlisted airport using an absent or stale confirmation."""
        values = self.values | {"departure_code": "ZZZ"}
        preview = self.post("/flights/new", values | {"action": "continue"})
        self.assertIn(b"Use ZZZ as entered", preview.data)
        for confirmation in ("", "XXX"):
            response = self.post("/flights/new", values | {
                "action": "save", "confirm_departure_code": confirmation})
            self.assertEqual(response.status_code, 400)
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM flights")[0]["n"], 0)
        self.assertEqual(self.post("/flights/new", values | {
            "action": "save", "confirm_departure_code": "ZZZ"}).status_code, 302)

    def test_search_matches_fields_and_combines_them(self):
        """Routes have direction, numbers match in full, and airline text is literal."""
        with app.app_context():
            def add(**changes):
                entry = flights.save(self.values | changes, self.owner)
                return f"/flights/{entry}"

            target = add(airline="AÉRO%_Air", flight_number="AY123")
            reverse = add(departure_code="AMS", arrival_code="HEL", airline="AÉRO%_Air")
            longer = add(airline="AÉROxxAir", flight_number="AY1234")
            unknown = add(departure_code="ZZZ")
            elsewhere = add(arrival_code="LHR", flight_number="AY123")
        guest = app.test_client()
        for query, expected in [
            ({"from": " hel "}, [elsewhere, longer, target]),
            ({"to": "ams"}, [unknown, longer, target]),
            ({"from": "zzz"}, [unknown]),
            ({"flight_number": " ay123 "}, [elsewhere, target]),
            ({"airline": " éro%_ "}, [reverse, target]),
            ({"airline": "' OR 1=1 --"}, []),
            ({"from": "hel", "to": "ams", "airline": "air", "flight_number": "ay123"}, [target]),
        ]:
            with self.subTest(query=query):
                response = guest.get("/", query_string=query)
                self.assertEqual(response.status_code, 200)
                links = Page(response).links
                self.assertEqual([link for link in links if link.startswith("/flights/")
                                      and link.rsplit("/", 1)[1].isdigit()], expected)
                if not expected:
                    self.assertIn(b"No flights match these filters.", response.data)

    def test_search_validation_preserves_filters(self):
        """Invalid input shows field errors; clearing the search restores the ordinary list."""
        path = self.create()
        for route in ("/", "/my-flights"):
            for key, value in (("from", "H"), ("to", "12A"), ("flight_number", "AY 123"),
                               ("airline", "x" * 101)):
                with self.subTest(route=route, key=key):
                    filters = {"from": "HEL", "airline": "Finnair", key: value}
                    response = self.client.get(route, query_string=filters)
                    self.assertEqual(response.status_code, 400)
                    page = Page(response)
                    self.assertEqual({k: page.values[k] for k in filters}, filters)
                    html = response.get_data(as_text=True)
                    self.assertIn(f'aria-describedby="error-{key}"', html)
                    self.assertIn(route, page.links)
                    self.assertNotIn(path, page.links)
            blank = self.client.get(route, query_string={"from": " "})
            self.assertIn(path, Page(blank).links)

    def test_filtered_pagination_preserves_scope_and_filters(self):
        """Following rendered links keeps the search, list order, and personal ownership."""
        values = self.values | {"airline": "A&B", "flight_number": "AY123"}
        with app.app_context():
            ids = [flights.save(values, self.owner) for _ in range(20)]
            older = flights.save(values | {"departure_date": "2020-01-01"}, self.owner)
            other = flights.save(values, self.other)
            flights.save(values | {"arrival_code": "LHR"}, self.owner)
        filters = {"from": "HEL", "to": "AMS", "airline": "&", "flight_number": "AY123"}
        for route, expected in (("/", [other, older, *reversed(ids)]),
                                ("/my-flights", [*reversed(ids), older])):
            response = self.client.get(route, query_string=filters)
            for page_number, batch in ((1, expected[:20]), (2, expected[20:])):
                with self.subTest(route=route, page=page_number):
                    self.assertEqual(response.status_code, 200)
                    links = Page(response).links
                    self.assertEqual([link for link in links if link.startswith("/flights/")
                                      and link.rsplit("/", 1)[1].isdigit()],
                                     [f"/flights/{entry}" for entry in batch])
                    paging = {link for link in links
                              if urlsplit(link).path == route and "page=" in link}
                    paging = [urlsplit(link) for link in paging]
                    self.assertEqual(len(paging), 1)
                    self.assertEqual(paging[0].path, route)
                    params = {key: [value] for key, value in filters.items()}
                    params["page"] = [str(3 - page_number)]
                    self.assertEqual(parse_qs(paging[0].query), params)
                    if page_number == 1:
                        response = self.client.get(paging[0].geturl())
        guest = app.test_client()
        self.assertEqual(guest.get("/my-flights", query_string=filters).status_code, 401)

    def test_finder_edits_only_the_draft_until_search(self):
        """Changing airports must not apply any draft fields, even the airline."""
        old = self.create(arrival_code="LHR", airline="Old airline")
        new = self.create(arrival_code="AMS", airline="A&B")
        for route in ("/", "/my-flights"):
            initial = self.client.get(route, query_string={"to": "LHR", "airline": "Old"})
            inputs = Page(initial).values
            inputs.pop("csrf_token", None)  # Belongs to the separate logout form.
            inputs.update(airline="A&B", find="to")
            finder = self.client.get(route, query_string=inputs)
            query = Page(finder).values | {"q": "schiphol"}
            query.pop("csrf_token", None)
            matches = self.client.get(route, query_string=query)
            self.assertIn(b"Amsterdam Airport Schiphol (AMS)", matches.data)
            for button, code in (({"cancel_find": "1"}, "LHR"), ({"pick": "AMS"}, "AMS")):
                returned = self.client.get(route, query_string=query | button)
                self.assertEqual(returned.status_code, 303)
                self.assertEqual(urlsplit(returned.location).fragment, "to")
                self.assertEqual(parse_qs(urlsplit(returned.location).query),
                                 {"to": ["LHR"], "airline": ["Old"]})
                page = self.client.get(returned.location)
                form = Page(page)
                self.assertEqual(form.values["to"], code)
                self.assertEqual("AMS — Amsterdam Airport Schiphol".encode() in page.data,
                                 "pick" in button)
                self.assertEqual(form.values["airline"], "A&B")
                self.assertIn(b"London Heathrow Airport (LHR)", page.data)
                self.assertIn(b"Airline: Old", page.data)
                self.assertIn(old, form.links)
                self.assertNotIn(new, form.links)
            form.values.pop("csrf_token", None)
            submitted = self.client.get(route, query_string=form.values, follow_redirects=True)
            self.assertEqual(submitted.request.path, route)
            self.assertEqual(dict(submitted.request.args), {"to": "AMS", "airline": "A&B"})
            self.assertIn(new, Page(submitted).links)
            self.assertNotIn(old, Page(submitted).links)
            self.assertEqual(self.client.get(route + "?find=other").status_code, 400)
        self.assertEqual(app.test_client().get("/my-flights?find=from&q=London").status_code, 401)

    def test_finder_preserves_unfiltered_page_with_an_incomplete_draft(self):
        """Page two remains visible while picking an airport with another field unfinished."""
        with app.app_context():
            ids = [flights.save(self.values, self.owner) for _ in range(21)]
        source = Page(self.client.get("/?page=2"))
        query = source.values | {"from": "H", "find": "to", "pick": "LHR"}
        response = self.client.get("/", query_string=query, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        page = Page(response)
        self.assertEqual(page.values["from"], "H")
        self.assertEqual(page.values["to"], "LHR")
        self.assertIn(b"Showing all public flights.", response.data)
        self.assertIn(b"Page 2", response.data)
        self.assertIn(f"/flights/{ids[0]}", page.links)
        self.assertNotIn(f"/flights/{ids[-1]}", page.links)

    def test_missing_flight_returns_not_found(self):
        """Missing entries have consistent status on view, edit, and delete."""
        for suffix in ("", "/edit", "/delete"):
            self.assertEqual(self.client.get("/flights/999" + suffix).status_code, 404)
