import json
from unittest.mock import patch

from django.test import TestCase

from apps.core.management.operations import archive_seed as helpers
from apps.core.tests.project.commands.resetdb.test_resetdb_helpers import FakeCommand, _string_open


class SeedCmsPagesTest(TestCase):
    def test_no_export_files(self):
        cmd = FakeCommand()
        with patch("apps.core.management.operations.archive_seed.glob.glob", return_value=[]):
            helpers._seed_cms_pages(cmd)
        self.assertIn("No cms_export_*.json found", cmd.stdout.text)

    def test_export_with_no_pages(self):
        cmd = FakeCommand()
        bundle = json.dumps({"pages": []})
        with (
            patch(
                "apps.core.management.operations.archive_seed.glob.glob",
                return_value=["/a/cms_export_1.json"],
            ),
            patch("builtins.open", new=_string_open(bundle)),
        ):
            helpers._seed_cms_pages(cmd)
        self.assertIn("No pages found in export file.", cmd.stdout.text)

    def test_processes_pages_and_reports_counts(self):
        cmd = FakeCommand()
        bundle = json.dumps({"pages": [{"slug": "a"}, {"slug": "b"}]})
        process_results = [
            {"success": True, "action": "create"},
            {"success": True, "action": "update"},
            {"errors": ["boom"]},
        ]
        with (
            patch(
                "apps.core.management.operations.archive_seed.glob.glob",
                return_value=["/a/cms_export_1.json", "/a/cms_export_2.json"],
            ),
            patch("builtins.open", new=_string_open(bundle)),
            patch(
                "apps.cms.admin.cms.page_admin.import_export.process_page_data",
                return_value=process_results,
            ) as process,
        ):
            helpers._seed_cms_pages(cmd)

        # latest file (sorted) selected
        process.assert_called_once()
        self.assertIn("1 created, 1 updated, 1 errors.", cmd.stdout.text)


class SeedMenusTest(TestCase):
    def test_missing_file(self):
        cmd = FakeCommand()
        with patch("apps.core.management.operations.archive_seed.os.path.exists", return_value=False):
            helpers._seed_menus(cmd)
        self.assertIn("No menus.json found", cmd.stdout.text)

    def test_creates_menu(self):
        from apps.cms.models import Menu

        cmd = FakeCommand()
        items = [{"label": "Home", "url": "/"}]
        with (
            patch("apps.core.management.operations.archive_seed.os.path.exists", return_value=True),
            patch("builtins.open", new=_string_open(json.dumps(items))),
        ):
            helpers._seed_menus(cmd)

        menu = Menu.objects.get(name="main_nav")
        self.assertEqual(menu.items, items)
        self.assertTrue(menu.is_active)
        self.assertIn("Created menu 'main_nav' with 1 top-level items.", cmd.stdout.text)

    def test_updates_existing_menu(self):
        from apps.cms.models import Menu

        Menu.objects.create(name="main_nav", display_name="Old", items=[], is_active=False)
        cmd = FakeCommand()
        items = [{"label": "A"}, {"label": "B"}]
        with (
            patch("apps.core.management.operations.archive_seed.os.path.exists", return_value=True),
            patch("builtins.open", new=_string_open(json.dumps(items))),
        ):
            helpers._seed_menus(cmd)

        self.assertIn("Updated menu 'main_nav' with 2 top-level items.", cmd.stdout.text)


class SeedFooterTest(TestCase):
    def test_missing_file(self):
        cmd = FakeCommand()
        with patch("apps.core.management.operations.archive_seed.os.path.exists", return_value=False):
            helpers._seed_footer(cmd)
        self.assertIn("No footer.json found", cmd.stdout.text)

    def test_creates_footer(self):
        from apps.cms.models import FooterContent

        cmd = FakeCommand()
        content = {"columns": [{"title": "About"}]}
        with (
            patch("apps.core.management.operations.archive_seed.os.path.exists", return_value=True),
            patch("builtins.open", new=_string_open(json.dumps(content))),
        ):
            helpers._seed_footer(cmd)

        footer = FooterContent.objects.get(slug="default")
        self.assertEqual(footer.content, content)
        self.assertTrue(footer.is_active)
        self.assertIn("Created footer 'default'.", cmd.stdout.text)

    def test_updates_existing_footer(self):
        from apps.cms.models import FooterContent

        FooterContent.objects.create(slug="default", name="Old", content={}, is_active=False)
        cmd = FakeCommand()
        content = {"columns": []}
        with (
            patch("apps.core.management.operations.archive_seed.os.path.exists", return_value=True),
            patch("builtins.open", new=_string_open(json.dumps(content))),
        ):
            helpers._seed_footer(cmd)

        self.assertIn("Updated footer 'default'.", cmd.stdout.text)
