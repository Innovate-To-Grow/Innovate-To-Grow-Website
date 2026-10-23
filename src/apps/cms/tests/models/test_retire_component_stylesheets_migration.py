import importlib

from django.apps import apps as global_apps
from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import StyleSheet
from apps.cms.services.styles.drift import load_seed_sheets

migration = importlib.import_module("apps.cms.migrations.0026_retire_component_stylesheets")
content_migration = importlib.import_module("apps.cms.migrations.0027_retire_content_stylesheets")

CONTENT_SHEETS = {"global", "cms-blocks", "cms-pages", "page-home"}


class RetireComponentStylesheetsMigrationTests(TestCase):
    def setUp(self):
        cache.clear()
        # The migrated test database is already past 0027; start from the state before 0026.
        content_migration.restore(global_apps, None)
        migration.restore(global_apps, None)

    def _active(self):
        return set(StyleSheet.objects.filter(is_active=True).values_list("name", flat=True))

    def test_reverse_brings_back_the_pre_migration_state(self):
        seeds = load_seed_sheets()
        for sheet in StyleSheet.objects.all():
            with self.subTest(sheet=sheet.name):
                self.assertEqual(sheet.is_active, seeds[sheet.name]["is_active"])
                self.assertEqual(sheet.description, seeds[sheet.name]["description"])

    def test_switches_off_exactly_the_component_sheets(self):
        before = self._active()
        migration.retire(global_apps, None)

        self.assertEqual(self._active(), before - set(migration.RETIRED_SHEETS))
        self.assertTrue(CONTENT_SHEETS <= self._active())
        self.assertFalse(set(migration.RETIRED_SHEETS) & self._active())

    def test_notes_where_the_css_lives_now_and_keeps_the_description(self):
        original = StyleSheet.objects.get(name="layout-menu").description
        migration.retire(global_apps, None)
        migration.retire(global_apps, None)

        description = StyleSheet.objects.get(name="layout-menu").description
        self.assertEqual(
            description,
            "Retired: the frontend bundle ships this CSS "
            "(pages/src/features/layout/components/MainMenu/MainMenu.css).\n" + original,
        )

    def test_leaves_a_sheet_an_admin_already_switched_off_alone(self):
        StyleSheet.objects.filter(name="page-news").update(is_active=False, description="Off for now.")
        migration.retire(global_apps, None)
        migration.restore(global_apps, None)

        sheet = StyleSheet.objects.get(name="page-news")
        self.assertFalse(sheet.is_active)
        self.assertEqual(sheet.description, "Off for now.")

    def test_reverse_switches_back_on_only_what_it_switched_off(self):
        before = {sheet.name: (sheet.is_active, sheet.description) for sheet in StyleSheet.objects.all()}
        migration.retire(global_apps, None)
        migration.restore(global_apps, None)

        after = {sheet.name: (sheet.is_active, sheet.description) for sheet in StyleSheet.objects.all()}
        self.assertEqual(after, before)

    def test_reverse_accepts_the_note_saved_with_any_line_ending(self):
        migration.retire(global_apps, None)
        sheet = StyleSheet.objects.get(name="auth")
        note, original = sheet.description.split("\n", 1)
        for stored in (f"{note}\r\n{original}", f"{note}{original}" if not original else f"{note}\r{original}"):
            with self.subTest(stored=stored[-20:]):
                StyleSheet.objects.filter(pk=sheet.pk).update(is_active=False, description=stored)
                migration.restore(global_apps, None)

                sheet.refresh_from_db()
                self.assertTrue(sheet.is_active)
                self.assertEqual(sheet.description, original)

    def test_a_missing_sheet_is_skipped(self):
        StyleSheet.objects.filter(name="maintenance").delete()
        migration.retire(global_apps, None)

        self.assertFalse(StyleSheet.objects.filter(name="maintenance").exists())
        self.assertFalse(StyleSheet.objects.get(name="auth").is_active)

    def test_the_served_stylesheet_keeps_only_the_content_sheets(self):
        migration.retire(global_apps, None)

        css = self.client.get("/layout/styles.css").content.decode()
        self.assertNotIn(".site-header", css)
        self.assertNotIn(".site-footer", css)
        self.assertNotIn(".maintenance-container", css)
        self.assertIn(".cms-rich-text", css)
