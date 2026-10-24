"""Migration 0031 drops the CMSPage.page_css column, but never a page's CSS."""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

migration = importlib.import_module("apps.cms.migrations.0031_remove_cmspage_page_css")


def _historical_apps(*pages):
    objects = Mock()
    objects.exclude.return_value.only.return_value.order_by.return_value = list(pages)
    apps = Mock()
    apps.get_model.return_value = SimpleNamespace(objects=objects)
    return apps, objects


def _page(route, status, page_css):
    return SimpleNamespace(route=route, status=status, page_css=page_css)


class RemovePageCssMigrationTests(SimpleTestCase):
    def test_guard_runs_before_the_column_goes(self):
        guard, remove = migration.Migration.operations
        self.assertIs(guard.code, migration.refuse_to_drop_page_css)
        self.assertEqual((remove.model_name, remove.name), ("cmspage", "page_css"))

    def test_proceeds_when_no_page_has_css(self):
        apps, objects = _historical_apps()

        migration.refuse_to_drop_page_css(apps, None)

        apps.get_model.assert_called_once_with("cms", "CMSPage")
        objects.exclude.assert_called_once_with(page_css="")

    def test_whitespace_only_css_is_not_kept(self):
        apps, _ = _historical_apps(_page("/about", "published", " \n\t"))

        migration.refuse_to_drop_page_css(apps, None)

    def test_stops_and_names_every_page_that_still_has_css(self):
        apps, _ = _historical_apps(
            _page("/about", "published", ".about-page h2 { color: red; }"),
            _page("/blank", "published", "  "),
            _page("/new-event", "draft", "h1 { margin: 0; }"),
        )

        with self.assertRaises(RuntimeError) as raised:
            migration.refuse_to_drop_page_css(apps, None)

        message = str(raised.exception)
        self.assertIn("/about (published), /new-event (draft).", message)
        self.assertNotIn("/blank", message)
