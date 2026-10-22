"""Drift in the migrated database, and the rules for the component sheets that migration 0026 switched off."""

import importlib

from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import StyleSheet
from apps.cms.services.styles.drift import (
    RETIRED_SHEETS,
    STATUS_IN_SYNC,
    STATUS_LABELS,
    STATUS_RETIRED,
    STATUS_SETTINGS_CHANGED,
    changed_settings,
    drift_report,
    drifted_sheets,
    has_drift,
    load_seed_sheets,
    seed_status_label,
    sheet_status,
)

migration = importlib.import_module("apps.cms.migrations.0026_retire_component_stylesheets")


class RetiredSheetDriftTests(TestCase):
    def setUp(self):
        cache.clear()
        self.seeds = load_seed_sheets()
        self.sheet = StyleSheet.objects.get(name="layout-menu")

    def test_the_drift_list_matches_the_migration(self):
        self.assertEqual(RETIRED_SHEETS, frozenset(migration.RETIRED_SHEETS))

    def test_a_retired_sheet_that_is_off_is_reported_as_retired(self):
        self.assertFalse(self.sheet.is_active)
        self.assertEqual(sheet_status(self.sheet, self.seeds), STATUS_RETIRED)
        self.assertEqual(seed_status_label(self.sheet), STATUS_LABELS[STATUS_RETIRED])
        self.assertEqual(changed_settings(self.sheet, self.seeds["layout-menu"]), [])

    def test_its_css_and_order_no_longer_matter_while_it_is_off(self):
        self.sheet.css += "\n.admin-edit { color: red; }\n"
        self.sheet.sort_order = 999
        self.sheet.save()

        self.assertEqual(sheet_status(self.sheet, self.seeds), STATUS_RETIRED)
        self.assertEqual(changed_settings(self.sheet, self.seeds["layout-menu"]), [])
        self.assertFalse(has_drift(drift_report()))

    def test_switching_a_retired_sheet_back_on_is_drift(self):
        self.sheet.is_active = True
        self.sheet.save()

        self.assertEqual(sheet_status(self.sheet, self.seeds), STATUS_SETTINGS_CHANGED)
        self.assertEqual(changed_settings(self.sheet, self.seeds["layout-menu"]), ["is_active"])
        self.assertEqual(drifted_sheets(drift_report()), ["layout-menu"])

    def test_deleting_a_retired_sheet_is_not_drift(self):
        self.sheet.delete()

        report = drift_report()
        self.assertEqual(report["missing_from_database"], ["layout-menu"])
        self.assertEqual(report["deleted_active_seed_sheets"], [])
        self.assertFalse(has_drift(report))

    def test_deleting_a_content_sheet_still_is(self):
        StyleSheet.objects.filter(name="global").delete()

        self.assertEqual(drifted_sheets(drift_report()), ["global (deleted)"])


class RealSeedTests(TestCase):
    """The migrated test database holds the repo seed with the component sheets retired, so nothing has drifted."""

    def setUp(self):
        cache.clear()

    def test_migrated_database_matches_the_seed(self):
        seeds = load_seed_sheets()
        self.assertTrue(seeds)
        self.assertEqual(set(StyleSheet.objects.values_list("name", flat=True)), set(seeds))

        for sheet in StyleSheet.objects.all():
            expected = STATUS_RETIRED if sheet.name in RETIRED_SHEETS else STATUS_IN_SYNC
            with self.subTest(sheet=sheet.name):
                self.assertEqual(sheet_status(sheet, seeds), expected)
                self.assertEqual(seed_status_label(sheet), STATUS_LABELS[expected])

        report = drift_report()
        self.assertTrue(report["seed_found"])
        self.assertEqual(
            report["counts"],
            {STATUS_IN_SYNC: len(seeds) - len(RETIRED_SHEETS), STATUS_RETIRED: len(RETIRED_SHEETS)},
        )
        self.assertEqual(report["missing_from_database"], [])
        self.assertEqual(report["deleted_active_seed_sheets"], [])
        self.assertEqual(drifted_sheets(report), [])
        self.assertFalse(has_drift(report))
