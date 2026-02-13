"""
Tests for import/export utilities and management commands.

Covers:
- Serialization (with and without file paths)
- Deserialization (create, update, file restoration)
- collect_component_files helper
- Round-trip (export -> import -> verify)
- export_pages / import_pages management commands
"""

import json
import tempfile
import zipfile
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase

from ..admin.import_export import (
    collect_component_files,
    deserialize_homepage,
    deserialize_page,
    serialize_homepage,
    serialize_page,
)
from ..models import (
    ComponentDataSource,
    HomePage,
    Page,
    PageComponent,
    PageComponentImage,
    UniformForm,
)


# ========================
# Serialization Tests
# ========================


class SerializePageTest(TestCase):
    def test_basic_format(self):
        page = Page.objects.create(title="About", slug="about", meta_title="About Us")
        data = serialize_page(page)

        self.assertEqual(data["export_type"], "page")
        self.assertEqual(data["export_version"], "1.0")
        self.assertIn("exported_at", data)
        self.assertEqual(data["page"]["title"], "About")
        self.assertEqual(data["page"]["slug"], "about")
        self.assertEqual(data["page"]["meta_title"], "About Us")
        self.assertEqual(data["components"], [])

    def test_with_components(self):
        page = Page.objects.create(title="Test", slug="test")
        PageComponent.objects.create(
            page=page, name="Hero", component_type="html", order=0,
            html_content="<h1>Hello</h1>", css_code="h1 { color: red; }",
        )
        data = serialize_page(page)

        self.assertEqual(len(data["components"]), 1)
        comp = data["components"][0]
        self.assertEqual(comp["name"], "Hero")
        self.assertEqual(comp["component_type"], "html")
        self.assertEqual(comp["html_content"], "<h1>Hello</h1>")
        self.assertEqual(comp["css_code"], "h1 { color: red; }")

    def test_include_files_false_excludes_file_fields(self):
        page = Page.objects.create(title="T", slug="t")
        comp = PageComponent.objects.create(
            page=page, name="C", component_type="html", order=0, html_content="<p>x</p>",
        )
        # Simulate a file field value
        comp.image.save("hero.png", ContentFile(b"PNG_DATA"), save=False)
        PageComponent.objects.filter(pk=comp.pk).update(image=comp.image.name)

        data = serialize_page(page, include_files=False)
        comp_data = data["components"][0]
        self.assertNotIn("image", comp_data)
        self.assertNotIn("css_file", comp_data)
        self.assertNotIn("background_image", comp_data)

    def test_include_files_true_includes_file_fields(self):
        page = Page.objects.create(title="T", slug="t")
        comp = PageComponent.objects.create(
            page=page, name="C", component_type="html", order=0, html_content="<p>x</p>",
        )
        comp.image.save("hero.png", ContentFile(b"PNG_DATA"), save=False)
        PageComponent.objects.filter(pk=comp.pk).update(image=comp.image.name)
        comp.refresh_from_db()

        data = serialize_page(page, include_files=True)
        comp_data = data["components"][0]
        self.assertIn("image", comp_data)
        self.assertIsNotNone(comp_data["image"])
        self.assertIn("hero", comp_data["image"])
        self.assertIn("css_file", comp_data)
        self.assertIsNone(comp_data["css_file"])  # not set
        self.assertIn("background_image", comp_data)

    def test_gallery_images_serialized(self):
        page = Page.objects.create(title="T", slug="t")
        comp = PageComponent.objects.create(
            page=page, name="Gallery", component_type="html", order=0, html_content="<div/>",
        )
        PageComponentImage.objects.create(
            component=comp, order=0, alt="Photo 1", caption="Cap 1",
        )
        data = serialize_page(page)
        images = data["components"][0]["images"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["alt"], "Photo 1")

    def test_data_source_ref_serialized(self):
        ds = ComponentDataSource.objects.create(
            source_name="my-api", source_url="/api/data/",
        )
        page = Page.objects.create(title="T", slug="t")
        PageComponent.objects.create(
            page=page, name="Dynamic", component_type="html", order=0,
            html_content="<p>d</p>", data_source=ds,
        )
        data = serialize_page(page)
        self.assertEqual(data["components"][0]["data_source_name"], "my-api")

    def test_form_ref_serialized(self):
        form = UniformForm.objects.create(name="Contact", slug="contact")
        page = Page.objects.create(title="T", slug="t")
        PageComponent.objects.create(
            page=page, name="Form", component_type="form", order=0,
            html_content="", form=form,
        )
        data = serialize_page(page)
        self.assertEqual(data["components"][0]["form_slug"], "contact")


class SerializeHomePageTest(TestCase):
    def test_basic_format(self):
        hp = HomePage.objects.create(name="Home V1")
        data = serialize_homepage(hp)
        self.assertEqual(data["export_type"], "homepage")
        self.assertEqual(data["homepage"]["name"], "Home V1")
        self.assertEqual(data["components"], [])

    def test_with_components(self):
        hp = HomePage.objects.create(name="Home")
        PageComponent.objects.create(
            home_page=hp, name="Welcome", component_type="html", order=0,
            html_content="<h1>Welcome</h1>",
        )
        data = serialize_homepage(hp)
        self.assertEqual(len(data["components"]), 1)


# ========================
# Deserialization Tests
# ========================


class DeserializePageTest(TestCase):
    def test_create_new_page(self):
        data = {
            "export_type": "page",
            "page": {"title": "New Page", "slug": "new-page"},
            "components": [
                {"name": "Body", "component_type": "html", "order": 0, "html_content": "<p>Hi</p>"},
            ],
        }
        page, warnings = deserialize_page(data)
        self.assertEqual(page.title, "New Page")
        self.assertEqual(page.slug, "new-page")
        self.assertEqual(page.status, "draft")
        self.assertEqual(page.components.count(), 1)

    def test_update_existing_page(self):
        Page.objects.create(title="Old", slug="existing", status="published")

        data = {
            "export_type": "page",
            "page": {"title": "Updated", "slug": "existing"},
            "components": [],
        }
        page, warnings = deserialize_page(data)
        self.assertEqual(page.title, "Updated")
        self.assertEqual(page.status, "draft")  # Reset to draft
        self.assertTrue(any("Updated existing" in w for w in warnings))

    def test_replaces_components(self):
        page = Page.objects.create(title="T", slug="replace-test")
        PageComponent.objects.create(
            page=page, name="Old", component_type="html", order=0, html_content="old",
        )

        data = {
            "export_type": "page",
            "page": {"title": "T", "slug": "replace-test"},
            "components": [
                {"name": "New", "component_type": "html", "order": 0, "html_content": "new"},
            ],
        }
        page, _ = deserialize_page(data)
        self.assertEqual(page.components.count(), 1)
        self.assertEqual(page.components.first().name, "New")

    def test_missing_slug_raises(self):
        data = {"export_type": "page", "page": {}, "components": []}
        with self.assertRaises(ValueError):
            deserialize_page(data)

    def test_resolves_data_source(self):
        ComponentDataSource.objects.create(source_name="api-source", source_url="/api/x/")
        data = {
            "export_type": "page",
            "page": {"slug": "ds-test", "title": "T"},
            "components": [
                {
                    "name": "C", "component_type": "html", "order": 0,
                    "html_content": "<p/>", "data_source_name": "api-source",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertIsNotNone(comp.data_source)
        self.assertEqual(comp.data_source.source_name, "api-source")

    def test_warns_missing_data_source(self):
        data = {
            "export_type": "page",
            "page": {"slug": "ds-warn", "title": "T"},
            "components": [
                {
                    "name": "C", "component_type": "html", "order": 0,
                    "html_content": "<p/>", "data_source_name": "nonexistent",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        self.assertTrue(any("nonexistent" in w for w in warnings))

    def test_resolves_form(self):
        UniformForm.objects.create(name="Contact", slug="contact")
        data = {
            "export_type": "page",
            "page": {"slug": "form-test", "title": "T"},
            "components": [
                {
                    "name": "F", "component_type": "form", "order": 0,
                    "html_content": "", "form_slug": "contact",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertIsNotNone(comp.form)
        self.assertEqual(comp.form.slug, "contact")

    def test_warns_missing_form(self):
        data = {
            "export_type": "page",
            "page": {"slug": "form-warn", "title": "T"},
            "components": [
                {
                    "name": "F", "component_type": "form", "order": 0,
                    "html_content": "", "form_slug": "missing-form",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        self.assertTrue(any("missing-form" in w for w in warnings))

    def test_file_map_restores_files(self):
        file_map = {
            "media/page_components/images/hero.png": b"PNG_FAKE_DATA",
        }
        data = {
            "export_type": "page",
            "page": {"slug": "file-test", "title": "T"},
            "components": [
                {
                    "name": "Hero", "component_type": "html", "order": 0,
                    "html_content": "<img/>",
                    "image": "page_components/images/hero.png",
                },
            ],
        }
        page, warnings = deserialize_page(data, file_map=file_map)
        comp = page.components.first()
        comp.refresh_from_db()
        self.assertTrue(comp.image.name)
        self.assertIn("hero", comp.image.name)

    def test_file_map_warns_missing_file(self):
        file_map = {}  # empty
        data = {
            "export_type": "page",
            "page": {"slug": "file-missing", "title": "T"},
            "components": [
                {
                    "name": "C", "component_type": "html", "order": 0,
                    "html_content": "<p/>",
                    "image": "page_components/images/nonexistent.png",
                },
            ],
        }
        page, warnings = deserialize_page(data, file_map=file_map)
        self.assertTrue(any("nonexistent.png" in w for w in warnings))

    def test_gallery_image_file_restored(self):
        file_map = {
            "media/page_components/images/gallery1.jpg": b"JPG_FAKE",
        }
        data = {
            "export_type": "page",
            "page": {"slug": "gallery-file", "title": "T"},
            "components": [
                {
                    "name": "Gallery", "component_type": "html", "order": 0,
                    "html_content": "<div/>",
                    "images": [
                        {"order": 0, "alt": "Pic 1", "image": "page_components/images/gallery1.jpg"},
                    ],
                },
            ],
        }
        page, warnings = deserialize_page(data, file_map=file_map)
        comp = page.components.first()
        img = comp.images.first()
        img.refresh_from_db()
        self.assertTrue(img.image.name)
        self.assertIn("gallery1", img.image.name)


class DeserializeHomePageTest(TestCase):
    def test_create_new(self):
        data = {
            "export_type": "homepage",
            "homepage": {"name": "New Home"},
            "components": [
                {"name": "Welcome", "component_type": "html", "order": 0, "html_content": "<h1>Hi</h1>"},
            ],
        }
        hp, warnings = deserialize_homepage(data)
        self.assertEqual(hp.name, "New Home")
        self.assertEqual(hp.status, "draft")
        self.assertFalse(hp.is_active)
        self.assertEqual(hp.components.count(), 1)

    def test_update_existing(self):
        HomePage.objects.create(name="Existing Home", status="published", is_active=False)
        data = {
            "export_type": "homepage",
            "homepage": {"name": "Existing Home"},
            "components": [],
        }
        hp, warnings = deserialize_homepage(data)
        self.assertEqual(hp.status, "draft")
        self.assertFalse(hp.is_active)
        self.assertTrue(any("Updated existing" in w for w in warnings))

    def test_missing_name_raises(self):
        data = {"export_type": "homepage", "homepage": {}, "components": []}
        with self.assertRaises(ValueError):
            deserialize_homepage(data)


# ========================
# Helper Tests
# ========================


class CollectComponentFilesTest(TestCase):
    def test_collects_all_file_paths(self):
        page = Page.objects.create(title="T", slug="collect-test")
        comp = PageComponent.objects.create(
            page=page, name="C", component_type="html", order=0, html_content="<p/>",
        )
        # Save files
        comp.image.save("hero.png", ContentFile(b"IMG"), save=False)
        comp.css_file.save("style.css", ContentFile(b"CSS"), save=False)
        PageComponent.objects.filter(pk=comp.pk).update(
            image=comp.image.name, css_file=comp.css_file.name,
        )
        comp.refresh_from_db()

        img = PageComponentImage.objects.create(component=comp, order=0)
        img.image.save("gallery.png", ContentFile(b"GAL"), save=False)
        PageComponentImage.objects.filter(pk=img.pk).update(image=img.image.name)

        paths = collect_component_files(page.components.all())
        self.assertIn(comp.image.name, paths)
        self.assertIn(comp.css_file.name, paths)
        self.assertIn(img.image.name, paths)

    def test_empty_components(self):
        page = Page.objects.create(title="T", slug="empty-test")
        paths = collect_component_files(page.components.all())
        self.assertEqual(paths, set())


# ========================
# Round-trip Tests
# ========================


class RoundTripTest(TestCase):
    def test_page_round_trip(self):
        """Export a page then import it to a new slug — data should match."""
        page = Page.objects.create(
            title="Round Trip", slug="round-trip",
            meta_description="A test page", meta_robots="index,follow",
        )
        PageComponent.objects.create(
            page=page, name="Body", component_type="html", order=0,
            html_content="<p>Content</p>", css_code="p { margin: 0; }",
            js_code="console.log('hi');",
        )

        # Export
        data = serialize_page(page)

        # Modify slug to create new page
        data["page"]["slug"] = "round-trip-copy"
        imported, warnings = deserialize_page(data)

        self.assertEqual(imported.title, "Round Trip")
        self.assertEqual(imported.slug, "round-trip-copy")
        self.assertEqual(imported.meta_description, "A test page")
        self.assertEqual(imported.components.count(), 1)
        comp = imported.components.first()
        self.assertEqual(comp.html_content, "<p>Content</p>")
        self.assertEqual(comp.css_code, "p { margin: 0; }")
        self.assertEqual(comp.js_code, "console.log('hi');")

    def test_homepage_round_trip(self):
        hp = HomePage.objects.create(name="RT Home")
        PageComponent.objects.create(
            home_page=hp, name="Welcome", component_type="html", order=0,
            html_content="<h1>Welcome</h1>",
        )

        data = serialize_homepage(hp)
        data["homepage"]["name"] = "RT Home Copy"
        imported, warnings = deserialize_homepage(data)

        self.assertEqual(imported.name, "RT Home Copy")
        self.assertEqual(imported.components.count(), 1)
        self.assertEqual(imported.components.first().html_content, "<h1>Welcome</h1>")


# ========================
# Management Command Tests
# ========================


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
                            "name": "Hero", "component_type": "html", "order": 0,
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
