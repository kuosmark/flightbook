"""Smoke coverage for the homepage's template and stylesheet integration."""

from html.parser import HTMLParser
import unittest
from unittest.mock import patch

from app import app


class StylesheetParser(HTMLParser):
    """Collect stylesheet references from the rendered HTML."""

    def __init__(self):
        super().__init__()
        self.stylesheets = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "link" and "stylesheet" in attributes.get("rel", "").split():
            self.stylesheets.append(attributes.get("href", ""))


class HomepageTest(unittest.TestCase):
    """Check that the homepage and its styles can be served together."""

    def test_homepage_and_stylesheets(self):
        """Render the real templates and load their referenced local stylesheets."""
        with (
            patch.dict(app.config, TESTING=True, SECRET_KEY="test-only"),
            app.test_client() as client,
        ):
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "text/html")

            parser = StylesheetParser()
            parser.feed(response.get_data(as_text=True))
            self.assertTrue(parser.stylesheets, "The homepage must link its stylesheet.")

            for stylesheet in parser.stylesheets:
                with self.subTest(stylesheet=stylesheet):
                    self.assertTrue(stylesheet.startswith("/static/"))
                    with client.get(stylesheet) as asset:
                        self.assertEqual(asset.status_code, 200)
                        self.assertEqual(asset.mimetype, "text/css")
                        self.assertTrue(asset.get_data().strip())
