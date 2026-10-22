import importlib

from django.apps import apps as global_apps
from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import SiteSettings, StyleSheet
from apps.cms.services.styles.tokens import render_tokens_css

migration = importlib.import_module("apps.cms.migrations.0027_retire_content_stylesheets")


class RetireContentStylesheetsMigrationTests(TestCase):
    def setUp(self):
        cache.clear()
        # The migrated test database is already past 0027; start from the state before it.
        migration.restore(global_apps, None)

    def _active(self):
        return set(StyleSheet.objects.filter(is_active=True).values_list("name", flat=True))

    def test_reverse_switches_the_content_sheets_back_on(self):
        self.assertEqual(self._active(), set(migration.RETIRED_SHEETS))

    def test_switches_off_every_remaining_seed_sheet(self):
        migration.retire(global_apps, None)

        self.assertEqual(self._active(), set())

    def test_notes_where_the_css_lives_now_and_keeps_the_description(self):
        original = StyleSheet.objects.get(name="global").description
        migration.retire(global_apps, None)
        migration.retire(global_apps, None)

        self.assertEqual(
            StyleSheet.objects.get(name="global").description,
            "Retired: the frontend bundle ships this CSS (pages/src/styles/contract/global/).\n" + original,
        )

    def test_reverse_switches_back_on_only_what_it_switched_off(self):
        StyleSheet.objects.filter(name="page-home").update(is_active=False, description="Off for now.")
        before = {sheet.name: (sheet.is_active, sheet.description) for sheet in StyleSheet.objects.all()}
        migration.retire(global_apps, None)
        migration.restore(global_apps, None)

        after = {sheet.name: (sheet.is_active, sheet.description) for sheet in StyleSheet.objects.all()}
        self.assertEqual(after, before)
        self.assertFalse(StyleSheet.objects.get(name="page-home").is_active)

    def test_the_served_stylesheet_is_only_the_design_tokens(self):
        migration.retire(global_apps, None)

        css = self.client.get("/layout/styles.css").content.decode()
        self.assertEqual(css, render_tokens_css(SiteSettings.load().design_tokens))
        self.assertNotIn(".cms-rich-text", css)
