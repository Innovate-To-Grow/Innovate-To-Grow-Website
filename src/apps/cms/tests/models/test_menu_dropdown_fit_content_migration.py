import importlib
import json
from pathlib import Path

from django.apps import apps as global_apps
from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import StyleSheet

migration = importlib.import_module("apps.cms.migrations.0025_menu_dropdown_fit_content")

STYLESHEETS_JSON = Path(migration.__file__).resolve().parent / "data" / "stylesheets.json"

FIXED = "".join(old for old, _ in migration.REPLACEMENTS)


class MenuDropdownFitContentMigrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sheet = StyleSheet.objects.get(name=migration.SHEET)
        # The fixed-width sheet production has before this migration, plus an admin edit.
        self.sheet.css = f".menu-dropdown {{\n{FIXED}}}\n\n/* admin edit */\n.x {{ color: red; }}\n"
        self.sheet.save()

    def test_sizes_both_panels_to_their_content(self):
        migration.fit_content(global_apps, None)
        migration.fit_content(global_apps, None)

        self.sheet.refresh_from_db()
        self.assertNotIn("  width: 362px;", self.sheet.css)
        self.assertNotIn("  width: 288px;", self.sheet.css)
        self.assertEqual(self.sheet.css.count("width: max-content;"), 2)
        self.assertIn("  min-width: 100%;\n  max-width: 362px;\n", self.sheet.css)
        self.assertIn("  max-width: 288px;\n", self.sheet.css)
        self.assertIn("/* admin edit */", self.sheet.css)

    def test_keeps_an_admin_width_edit(self):
        self.sheet.css = self.sheet.css.replace("width: 362px;", "width: 400px;")
        self.sheet.save()
        migration.fit_content(global_apps, None)

        self.sheet.refresh_from_db()
        self.assertIn("width: 400px;", self.sheet.css)
        self.assertEqual(self.sheet.css.count("width: max-content;"), 1)

    def test_reverse_restores_the_fixed_widths(self):
        before = self.sheet.css
        migration.fit_content(global_apps, None)
        migration.fixed_width(global_apps, None)

        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.css, before)

    def test_seed_sheet_carries_the_content_widths_for_new_databases(self):
        records = json.loads(STYLESHEETS_JSON.read_text(encoding="utf-8"))
        css = next(r["fields"]["css"] for r in records if r["fields"]["name"] == migration.SHEET)
        for _, new in migration.REPLACEMENTS:
            self.assertIn(new, css)
