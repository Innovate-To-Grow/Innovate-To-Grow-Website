import hashlib
from pathlib import Path

from django.test import SimpleTestCase

DATA_DIR = Path(__file__).resolve().parents[2] / "migrations" / "data"

# Landed migrations (0004, 0016-0018, 0021, 0022, 0024, 0025) read this file on every new database.
STYLESHEETS_SHA256 = "f1084f1477d0b3b0bf0c5ea92fabe16351d957c77c4e4939cc2d4b67abea017d"


class MigrationDataFrozenTests(SimpleTestCase):
    def test_the_stylesheet_seed_is_unchanged(self):
        digest = hashlib.sha256((DATA_DIR / "stylesheets.json").read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            STYLESHEETS_SHA256,
            "migrations/data/stylesheets.json is read by landed migrations and must not change; "
            "edit the CSS in pages/src instead (see migrations/data/README.md).",
        )
