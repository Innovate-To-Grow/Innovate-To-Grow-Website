"""Migration 0032 moves the untouched 75ch prose cap to "none", and back on reverse."""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

migration = importlib.import_module("apps.cms.migrations.0032_prose_full_width")


def _settings(design_tokens):
    return SimpleNamespace(design_tokens=design_tokens, save=Mock())


def _historical_apps(*rows):
    apps = Mock()
    apps.get_model.return_value = SimpleNamespace(objects=SimpleNamespace(all=lambda: list(rows)))
    return apps


class ProseFullWidthMigrationTests(SimpleTestCase):
    def test_runs_forward_and_back(self):
        (operation,) = migration.Migration.operations
        self.assertIs(operation.code, migration.full_width)
        self.assertIs(operation.reverse_code, migration.capped)

    def test_untouched_cap_becomes_none(self):
        row = _settings({"layout": {"page_max_width": "1170px", "prose_max_width": "75ch"}})

        migration.full_width(_historical_apps(row), None)

        self.assertEqual(row.design_tokens["layout"], {"page_max_width": "1170px", "prose_max_width": "none"})
        row.save.assert_called_once_with(update_fields=["design_tokens"])

    def test_an_admin_value_is_kept(self):
        row = _settings({"layout": {"prose_max_width": "90ch"}})

        migration.full_width(_historical_apps(row), None)

        self.assertEqual(row.design_tokens["layout"]["prose_max_width"], "90ch")
        row.save.assert_not_called()

    def test_rows_without_the_token_are_left_alone(self):
        rows = [_settings({}), _settings({"layout": "not a group"}), _settings(None), _settings({"colors": {}})]

        migration.full_width(_historical_apps(*rows), None)

        for row in rows:
            row.save.assert_not_called()

    def test_reverse_restores_the_cap(self):
        full = _settings({"layout": {"prose_max_width": "none"}})
        custom = _settings({"layout": {"prose_max_width": "960px"}})

        migration.capped(_historical_apps(full, custom), None)

        self.assertEqual(full.design_tokens["layout"]["prose_max_width"], "75ch")
        full.save.assert_called_once_with(update_fields=["design_tokens"])
        custom.save.assert_not_called()
