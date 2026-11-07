"""Boundary cases for the flight list's page navigation."""

import unittest

from app import flight_pagination


class PaginationTest(unittest.TestCase):
    """Keep navigation short while retaining nearby pages."""

    def test_middle_of_long_list(self):
        """Both ends stay reachable without a link for every page."""
        pagination = flight_pagination(6, 221)
        self.assertEqual(pagination["pages"], [1, None, 5, 6, 7, None, 12])
        self.assertEqual((pagination["start"], pagination["end"]), (101, 120))
