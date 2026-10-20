import importlib
import json
from pathlib import Path

from django.apps import apps as global_apps
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.cms.models import SiteSettings, StyleSheet
from apps.cms.models.content.layout.site_settings import default_design_tokens

migration = importlib.import_module("apps.cms.migrations.0022_audit_fixes_styles")

STYLESHEETS_JSON = Path(migration.__file__).resolve().parent / "data" / "stylesheets.json"


class TokenTests(SimpleTestCase):
    def test_added_tokens_are_model_defaults(self):
        defaults = default_design_tokens()
        for group, values in migration.ADDED_TOKENS.items():
            for key, value in values.items():
                self.assertEqual(defaults[group][key], value)

    def test_adds_a_missing_token(self):
        tokens = migration.add_tokens({"layout": {"page_max_width": "1170px"}})
        self.assertEqual(tokens["layout"], {"page_max_width": "1170px", "prose_max_width": "75ch"})

    def test_keeps_a_value_an_admin_set(self):
        tokens = migration.add_tokens({"layout": {"prose_max_width": "68ch"}})
        self.assertEqual(tokens["layout"]["prose_max_width"], "68ch")

    def test_handles_empty_tokens(self):
        self.assertEqual(migration.add_tokens(None), migration.ADDED_TOKENS)

    def test_remove_drops_only_the_value_it_added(self):
        self.assertEqual(migration.remove_tokens(migration.add_tokens({"layout": {}})), {"layout": {}})
        self.assertEqual(
            migration.remove_tokens({"layout": {"prose_max_width": "68ch"}}),
            {"layout": {"prose_max_width": "68ch"}},
        )


class ForwardMigrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_adds_the_token_to_site_settings(self):
        settings = SiteSettings.load()
        settings.design_tokens = {"layout": {"page_max_width": "1170px"}}
        settings.save()

        migration.update_design_tokens(global_apps, None)

        settings.refresh_from_db()
        self.assertEqual(settings.design_tokens["layout"]["prose_max_width"], "75ch")
        self.assertEqual(settings.design_tokens["layout"]["page_max_width"], "1170px")

    def test_serves_the_token_as_a_css_variable(self):
        settings = SiteSettings.load()
        settings.design_tokens = {"layout": {}}
        settings.save()
        migration.update_design_tokens(global_apps, None)

        response = self.client.get("/layout/styles.css")

        self.assertIn("--itg-prose-max-width: 75ch;", response.content.decode())

    def test_syncs_the_touched_sheets_from_the_seed(self):
        StyleSheet.objects.filter(name="auth").update(css="/* edited in admin */")

        migration.sync_stylesheets(global_apps, None)

        records = {r["fields"]["name"]: r["fields"] for r in json.loads(STYLESHEETS_JSON.read_text())}
        for name in migration.SYNCED_SHEETS:
            self.assertEqual(StyleSheet.objects.get(name=name).css, records[name]["css"])

    def test_leaves_other_sheets_alone(self):
        StyleSheet.objects.filter(name="maintenance").update(css="/* edited in admin */")

        migration.sync_stylesheets(global_apps, None)

        self.assertEqual(StyleSheet.objects.get(name="maintenance").css, "/* edited in admin */")
        self.assertNotIn("maintenance", migration.SYNCED_SHEETS)

    def test_keeps_the_replaced_css_as_an_inactive_copy(self):
        StyleSheet.objects.filter(name="auth").update(css="/* edited in admin */")

        migration.sync_stylesheets(global_apps, None)

        backup = StyleSheet.objects.get(name="auth-pre-audit-fixes")
        self.assertEqual(backup.css, "/* edited in admin */")
        self.assertFalse(backup.is_active)

    def test_restore_puts_the_copied_css_back(self):
        StyleSheet.objects.filter(name="auth").update(css="/* edited in admin */")
        migration.sync_stylesheets(global_apps, None)

        migration.restore_stylesheets(global_apps, None)

        self.assertEqual(StyleSheet.objects.get(name="auth").css, "/* edited in admin */")
        self.assertFalse(StyleSheet.objects.filter(name="auth-pre-audit-fixes").exists())
