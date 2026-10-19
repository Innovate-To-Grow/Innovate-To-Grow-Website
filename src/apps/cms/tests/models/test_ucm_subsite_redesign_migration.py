import importlib
import json
from pathlib import Path

from django.apps import apps as global_apps
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.cms.models import SiteSettings, StyleSheet
from apps.cms.models.content.layout.site_settings import default_design_tokens

migration = importlib.import_module("apps.cms.migrations.0021_ucm_subsite_redesign")
audit_fixes_migration = importlib.import_module("apps.cms.migrations.0022_audit_fixes_styles")

STYLESHEETS_JSON = Path(migration.__file__).resolve().parent / "data" / "stylesheets.json"


class MergeTokensTests(SimpleTestCase):
    def test_new_defaults_match_the_model_defaults(self):
        # The migration embeds a literal copy so it stays stable; with the tokens later migrations
        # add, it must agree with the model today.
        self.assertEqual(audit_fixes_migration.add_tokens(migration.NEW_DEFAULT_TOKENS), default_design_tokens())

    def test_replaces_tokens_that_still_hold_the_previous_default(self):
        merged = migration.merge_tokens(migration.PREVIOUS_DEFAULT_TOKENS)
        self.assertEqual(merged, migration.NEW_DEFAULT_TOKENS)

    def test_keeps_values_an_admin_changed(self):
        current = json.loads(json.dumps(migration.PREVIOUS_DEFAULT_TOKENS))
        current["colors"]["accent_gold"] = "#123456"
        current["layout"]["page_max_width"] = "1300px"
        merged = migration.merge_tokens(current)
        self.assertEqual(merged["colors"]["accent_gold"], "#123456")
        self.assertEqual(merged["layout"]["page_max_width"], "1300px")
        self.assertEqual(merged["colors"]["primary"], "#0f2d52")

    def test_keeps_admin_only_tokens_and_groups(self):
        current = {"colors": {"brand_extra": "#abcdef"}, "custom": {"x": "1"}}
        merged = migration.merge_tokens(current)
        self.assertEqual(merged["colors"]["brand_extra"], "#abcdef")
        self.assertEqual(merged["custom"], {"x": "1"})
        self.assertEqual(merged["colors"]["secondary"], "#005487")

    def test_handles_empty_tokens(self):
        self.assertEqual(migration.merge_tokens(None), migration.NEW_DEFAULT_TOKENS)
        self.assertEqual(migration.merge_tokens({}), migration.NEW_DEFAULT_TOKENS)

    def test_unmerge_returns_the_previous_defaults(self):
        merged = migration.merge_tokens(migration.PREVIOUS_DEFAULT_TOKENS)
        self.assertEqual(migration.unmerge_tokens(merged), migration.PREVIOUS_DEFAULT_TOKENS)

    def test_unmerge_keeps_values_an_admin_changed(self):
        current = json.loads(json.dumps(migration.PREVIOUS_DEFAULT_TOKENS))
        current["colors"]["accent_gold"] = "#123456"
        current["custom"] = {"x": "1"}
        merged = migration.merge_tokens(current)
        merged["colors"]["secondary"] = "#222222"

        restored = migration.unmerge_tokens(merged)

        self.assertEqual(restored["colors"]["accent_gold"], "#123456")
        self.assertEqual(restored["colors"]["secondary"], "#222222")
        self.assertEqual(restored["colors"]["primary_hover"], "#1a4a7a")
        self.assertNotIn("footer_bg", restored["colors"])
        self.assertEqual(restored["custom"], {"x": "1"})


class ForwardMigrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_updates_site_settings_tokens(self):
        settings = SiteSettings.load()
        tokens = json.loads(json.dumps(migration.PREVIOUS_DEFAULT_TOKENS))
        tokens["colors"]["error"] = "#ff0000"
        settings.design_tokens = tokens
        settings.save()

        migration.update_design_tokens(global_apps, None)

        settings.refresh_from_db()
        self.assertEqual(settings.design_tokens["colors"]["primary"], "#0f2d52")
        self.assertEqual(settings.design_tokens["colors"]["error"], "#ff0000")
        self.assertEqual(
            settings.design_tokens["typography"]["font_family_body"],
            default_design_tokens()["typography"]["font_family_body"],
        )

    def test_restore_returns_tokens_to_the_previous_defaults(self):
        settings = SiteSettings.load()
        settings.design_tokens = migration.merge_tokens(migration.PREVIOUS_DEFAULT_TOKENS)
        settings.save()

        migration.restore_design_tokens(global_apps, None)

        settings.refresh_from_db()
        self.assertEqual(settings.design_tokens, migration.PREVIOUS_DEFAULT_TOKENS)

    def test_syncs_every_stylesheet_from_the_seed(self):
        StyleSheet.objects.filter(name="layout-footer").update(css="/* edited in admin */")
        StyleSheet.objects.filter(name="global").delete()

        migration.sync_stylesheets(global_apps, None)

        records = json.loads(STYLESHEETS_JSON.read_text())
        for record in records:
            sheet = StyleSheet.objects.get(name=record["fields"]["name"])
            self.assertEqual(sheet.css, record["fields"]["css"])
            self.assertEqual(sheet.sort_order, record["fields"]["sort_order"])
            self.assertTrue(sheet.is_active)

    def test_keeps_the_replaced_css_as_an_inactive_copy(self):
        footer = StyleSheet.objects.get(name="layout-footer")
        StyleSheet.objects.filter(pk=footer.pk).update(css="/* edited in admin */")

        migration.sync_stylesheets(global_apps, None)

        backup = StyleSheet.objects.get(name="layout-footer-pre-redesign")
        self.assertEqual(backup.css, "/* edited in admin */")
        self.assertFalse(backup.is_active)
        self.assertEqual(backup.sort_order, footer.sort_order)
        self.assertIn("layout-footer", backup.description)

    def test_copies_only_sheets_whose_css_changes(self):
        StyleSheet.objects.filter(name="layout-footer").update(css="/* edited in admin */")
        StyleSheet.objects.filter(name="global").delete()

        migration.sync_stylesheets(global_apps, None)

        copies = StyleSheet.objects.filter(name__endswith=migration.BACKUP_SUFFIX)
        self.assertEqual(list(copies.values_list("name", flat=True)), ["layout-footer-pre-redesign"])

    def test_a_second_run_keeps_the_first_copy(self):
        StyleSheet.objects.filter(name="layout-footer").update(css="/* edited in admin */")
        migration.sync_stylesheets(global_apps, None)
        StyleSheet.objects.filter(name="layout-footer").update(css="/* edited again */")

        migration.sync_stylesheets(global_apps, None)

        backup = StyleSheet.objects.get(name="layout-footer-pre-redesign")
        self.assertEqual(backup.css, "/* edited in admin */")

    def test_copied_css_is_not_served(self):
        StyleSheet.objects.filter(name="layout-footer").update(css=".old-footer { color: red; }")
        migration.sync_stylesheets(global_apps, None)

        response = self.client.get("/layout/styles.css")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(".old-footer", response.content.decode())

    def test_restore_puts_the_copied_css_back(self):
        StyleSheet.objects.filter(name="layout-footer").update(css="/* edited in admin */")
        migration.sync_stylesheets(global_apps, None)

        migration.restore_stylesheets(global_apps, None)

        self.assertEqual(StyleSheet.objects.get(name="layout-footer").css, "/* edited in admin */")
        self.assertFalse(StyleSheet.objects.filter(name="layout-footer-pre-redesign").exists())

    def test_restore_keeps_serving_a_sheet_switched_to_its_copy(self):
        StyleSheet.objects.filter(name="layout-footer").update(css="/* edited in admin */")
        migration.sync_stylesheets(global_apps, None)
        StyleSheet.objects.filter(name="layout-footer").update(is_active=False)
        StyleSheet.objects.filter(name="layout-footer-pre-redesign").update(is_active=True)

        migration.restore_stylesheets(global_apps, None)

        footer = StyleSheet.objects.get(name="layout-footer")
        self.assertEqual(footer.css, "/* edited in admin */")
        self.assertTrue(footer.is_active)

    def test_restore_keeps_a_copy_whose_sheet_is_gone(self):
        StyleSheet.objects.filter(name="layout-footer").update(css="/* edited in admin */")
        migration.sync_stylesheets(global_apps, None)
        StyleSheet.objects.filter(name="layout-footer").delete()

        migration.restore_stylesheets(global_apps, None)

        self.assertEqual(StyleSheet.objects.get(name="layout-footer-pre-redesign").css, "/* edited in admin */")
