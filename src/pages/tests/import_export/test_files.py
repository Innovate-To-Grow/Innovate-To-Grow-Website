"""
Tests for import/export file restoration and round-trip integrity.

Covers:
- DeserializePageTest (file-related): Google Sheet resolution, file map
  restoration, gallery image file restoration
- RoundTripTest: export -> import -> verify for pages and homepages
"""

from django.test import TestCase

from ...admin.content.import_export import (
    deserialize_homepage,
    deserialize_page,
    serialize_homepage,
    serialize_page,
)
from ...models import (
    GoogleSheet,
    HomePage,
    Page,
    PageComponent,
    PageComponentPlacement,
)


class DeserializePageFileTest(TestCase):
    """Deserialization tests that involve Google Sheets and file maps."""

    def test_resolves_google_sheet(self):
        GoogleSheet.objects.create(
            name="Public Table",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
        )
        data = {
            "export_type": "page",
            "page": {"slug": "google-sheet-test", "title": "T"},
            "components": [
                {
                    "name": "Sheet Component",
                    "component_type": "google_sheet",
                    "order": 0,
                    "google_sheet_name": "Public Table",
                    "google_sheet_style": "compact",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertEqual(comp.component_type, "google_sheet")
        self.assertIsNotNone(comp.google_sheet)
        self.assertEqual(comp.google_sheet.name, "Public Table")
        self.assertEqual(comp.google_sheet_style, "compact")

    def test_missing_google_sheet_falls_back_to_html(self):
        data = {
            "export_type": "page",
            "page": {"slug": "google-sheet-missing", "title": "T"},
            "components": [
                {
                    "name": "Missing Sheet Component",
                    "component_type": "google_sheet",
                    "order": 0,
                    "html_content": "<p>Fallback</p>",
                    "google_sheet_name": "missing-sheet",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertEqual(comp.component_type, "html")
        self.assertIsNone(comp.google_sheet)
        self.assertTrue(any("missing-sheet" in w for w in warnings))

    def test_file_map_restores_files(self):
        file_map = {
            "media/page_components/images/hero.png": b"PNG_FAKE_DATA",
        }
        data = {
            "export_type": "page",
            "page": {"slug": "file-test", "title": "T"},
            "components": [
                {
                    "name": "Hero",
                    "component_type": "html",
                    "order": 0,
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
                    "name": "C",
                    "component_type": "html",
                    "order": 0,
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
                    "name": "Gallery",
                    "component_type": "html",
                    "order": 0,
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


class RoundTripTest(TestCase):
    def test_page_round_trip(self):
        """Export a page then import it to a new slug -- data should match."""
        page = Page.objects.create(
            title="Round Trip",
            slug="round-trip",
            meta_description="A test page",
            meta_robots="index,follow",
        )
        comp = PageComponent.objects.create(
            name="Body",
            component_type="html",
            html_content="<p>Content</p>",
            css_code="p { margin: 0; }",
            js_code="console.log('hi');",
        )
        PageComponentPlacement.objects.create(component=comp, page=page, order=0)

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
        comp = PageComponent.objects.create(
            name="Welcome",
            component_type="html",
            html_content="<h1>Welcome</h1>",
        )
        PageComponentPlacement.objects.create(component=comp, home_page=hp, order=0)

        data = serialize_homepage(hp)
        data["homepage"]["name"] = "RT Home Copy"
        imported, warnings = deserialize_homepage(data)

        self.assertEqual(imported.name, "RT Home Copy")
        self.assertEqual(imported.components.count(), 1)
        self.assertEqual(imported.components.first().html_content, "<h1>Welcome</h1>")
