import importlib
import json
from pathlib import Path

from django.apps import apps as global_apps
from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import StyleSheet

migration = importlib.import_module("apps.cms.migrations.0024_member_button_label_style")

STYLESHEETS_JSON = Path(migration.__file__).resolve().parent / "data" / "stylesheets.json"


class MemberButtonLabelStyleMigrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sheet = StyleSheet.objects.get(name=migration.SHEET)
        # An admin's sheet without the block, as production has it before this migration.
        self.sheet.css = ".member-button {\n  text-decoration: underline;\n}\n\n/* admin edit */\n.x { color: red; }\n"
        self.sheet.save()

    def test_appends_the_block_once_and_keeps_admin_edits(self):
        migration.add_block(global_apps, None)
        migration.add_block(global_apps, None)

        self.sheet.refresh_from_db()
        self.assertTrue(self.sheet.css.startswith(".member-button {\n  text-decoration: underline;"))
        self.assertIn("/* admin edit */", self.sheet.css)
        self.assertEqual(self.sheet.css.count(migration.MARKER), 1)
        # Appended after the rule it overrides.
        self.assertGreater(self.sheet.css.index(migration.MARKER), self.sheet.css.index("text-decoration: underline"))

    def test_reverse_removes_only_the_block(self):
        before = self.sheet.css
        migration.add_block(global_apps, None)
        migration.remove_block(global_apps, None)

        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.css, before)

    def test_served_stylesheet_drops_the_underline(self):
        migration.add_block(global_apps, None)

        css = self.client.get("/layout/styles.css").content.decode()
        self.assertIn(".member-label {\n  max-width: 16rem;", css)
        self.assertRegex(css, r"\.member-button \{\n  text-decoration: none;\n\}")

    def test_seed_sheet_carries_the_block_for_new_databases(self):
        records = json.loads(STYLESHEETS_JSON.read_text(encoding="utf-8"))
        css = next(r["fields"]["css"] for r in records if r["fields"]["name"] == migration.SHEET)
        self.assertTrue(css.endswith(migration.BLOCK))
