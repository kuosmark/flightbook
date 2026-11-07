"""Local signing keys persist across app starts and yield to explicit configuration."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from session_key import load_key


class SessionKeyTest(unittest.TestCase):
    """Check first-run and subsequent-start behavior in an isolated directory."""

    @patch.dict(os.environ, {"FLIGHTBOOK_SECRET_KEY": ""})
    def test_init_creates_one_private_key(self):
        """Loading cannot create a key, and repeated initialization cannot rotate it."""
        with TemporaryDirectory() as root:
            directory = Path(root) / "instance"
            self.assertIsNone(load_key(directory))
            self.assertFalse(directory.exists())
            original = load_key(directory, create=True)
            self.assertEqual(len(original), 32)
            self.assertEqual(load_key(directory, create=True), original)
            self.assertEqual(load_key(directory), original)
            if os.name == "posix":
                self.assertEqual((directory / "session.key").stat().st_mode & 0o077, 0)
            with patch.dict(os.environ, FLIGHTBOOK_SECRET_KEY="configured"):
                self.assertEqual(load_key(directory), "configured")
            self.assertEqual(load_key(directory), original)

    @patch.dict(os.environ, {"FLIGHTBOOK_SECRET_KEY": "configured"})
    def test_configured_key_skips_local_setup(self):
        """An explicit key works without creating a secret on disk."""
        with TemporaryDirectory() as root:
            directory = Path(root) / "instance"
            self.assertEqual(load_key(directory, create=True), "configured")
            self.assertFalse(directory.exists())
