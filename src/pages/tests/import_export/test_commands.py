"""
Tests for export_pages and import_pages management commands.

Covers:
- ExportPagesCommandTest: export all, specific slug, homepage, error handling
- ImportPagesCommandTest: import page, media, dry-run, homepage, backward compat
"""

import json
import tempfile
import zipfile
from io import BytesIO

from django.core.management import call_command
from django.test import TestCase

from ...models import (
    HomePage,
    Page,
)


class ExportPagesCommandTest(TestCase):
    def test_export_all_pages_to_file(self):
        Page.objects.create(title="P1", slug="p1")
        Page.objects.create(title="P2", slug="p2")

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name

        call_command("export_pages", "--all", "-o", tmp_path)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            self.assertIn("manifest.json", zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["export_version"], "2.0")
            self.assertEqual(len(manifest["entries"]), 2)

    def test_export_specific_slug(self):
        Page.objects.create(title="Target", slug="target")
        Page.objects.create(title="Other", slug="other")

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name

        call_command("export_pages", "target", "-o", tmp_path)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(len(manifest["entries"]), 1)
            self.assertEqual(manifest["entries"][0]["page"]["slug"], "target")

    def test_export_homepage(self):
        HomePage.objects.create(name="Home Test")

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name

        call_command("export_pages", "--type", "homepage", "--all", "-o", tmp_path)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(len(manifest["entries"]), 1)
            self.assertEqual(manifest["entries"][0]["export_type"], "homepage")

    def test_export_no_slugs_no_all_raises(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("export_pages")


class ImportPagesCommandTest(TestCase):
    def _create_zip(self, manifest_data):
        """Helper: create a ZIP bytes buffer with a manifest.json."""
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))
        buf.seek(0)
        return buf

    def _write_zip_to_file(self, manifest_data, media_files=None):
        """Helper: write a ZIP to a temp file, return path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        with zipfile.ZipFile(tmp, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))
            if media_files:
                for archive_path, data in media_files.items():
                    zf.writestr(archive_path, data)
        tmp.close()
        return tmp.name

    def test_import_page_from_zip(self):
        manifest = {
            "export_version": "2.0",
            "entries": [
                {
                    "export_type": "page",
                    "page": {"title": "Imported", "slug": "imported"},
                    "components": [
                        {"name": "Body", "component_type": "html", "order": 0, "html_content": "<p>Hi</p>"},
                    ],
                }
            ],
        }
        path = self._write_zip_to_file(manifest)
        call_command("import_pages", path)

        page = Page.objects.get(slug="imported")
        self.assertEqual(page.title, "Imported")
        self.assertEqual(page.components.count(), 1)

    def test_import_with_media(self):
        manifest = {
            "export_version": "2.0",
            "entries": [
                {
                    "export_type": "page",
                    "page": {"title": "Media Page", "slug": "media-page"},
                    "components": [
                        {
                            "name": "Hero",
                            "component_type": "html",
                            "order": 0,
                            "html_content": "<img/>",
                            "image": "page_components/images/test-hero.png",
                        },
                    ],
                }
            ],
        }
        media_files = {"media/page_components/images/test-hero.png": b"FAKE_PNG_DATA"}
        path = self._write_zip_to_file(manifest, media_files)
        call_command("import_pages", path)

        page = Page.objects.get(slug="media-page")
        comp = page.components.first()
        comp.refresh_from_db()
        self.assertTrue(comp.image.name)

    def test_dry_run_does_not_create(self):
        manifest = {
            "export_version": "2.0",
            "entries": [
                {
                    "export_type": "page",
                    "page": {"title": "Ghost", "slug": "ghost"},
                    "components": [],
                }
            ],
        }
        path = self._write_zip_to_file(manifest)
        call_command("import_pages", path, "--dry-run")

        self.assertFalse(Page.objects.filter(slug="ghost").exists())

    def test_import_homepage(self):
        manifest = {
            "export_version": "2.0",
            "entries": [
                {
                    "export_type": "homepage",
                    "homepage": {"name": "Imported Home"},
                    "components": [],
                }
            ],
        }
        path = self._write_zip_to_file(manifest)
        call_command("import_pages", path)

        self.assertTrue(HomePage.objects.filter(name="Imported Home").exists())

    def test_backward_compat_single_entry(self):
        """v1.0 format without 'entries' key should still work."""
        manifest = {
            "export_version": "1.0",
            "export_type": "page",
            "page": {"title": "Legacy", "slug": "legacy"},
            "components": [],
        }
        path = self._write_zip_to_file(manifest)
        call_command("import_pages", path)

        self.assertTrue(Page.objects.filter(slug="legacy").exists())
