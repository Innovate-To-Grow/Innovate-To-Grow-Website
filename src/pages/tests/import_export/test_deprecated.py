"""
Tests for deprecated component type fallback during import.

Covers:
- ImportDeprecatedComponentTypeTest: template/widget -> html conversion,
  valid types pass-through, Google Sheet pass-through, homepage fallback,
  unknown type fallback
"""

from django.test import TestCase

from ...admin.content.import_export import (
    deserialize_homepage,
    deserialize_page,
)
from ...models import (
    GoogleSheet,
)


class ImportDeprecatedComponentTypeTest(TestCase):
    """Test that importing old component types (template, widget) falls back to html."""

    def test_deprecated_template_type_converts_to_html(self):
        data = {
            "export_type": "page",
            "page": {"title": "Old Page", "slug": "old-template"},
            "components": [
                {
                    "name": "Legacy",
                    "component_type": "template",
                    "order": 0,
                    "html_content": "<p>Legacy</p>",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertEqual(comp.component_type, "html")
        self.assertTrue(any("template" in w and "defaulted to 'html'" in w for w in warnings))

    def test_deprecated_widget_type_converts_to_html(self):
        data = {
            "export_type": "page",
            "page": {"title": "Old Page", "slug": "old-widget"},
            "components": [
                {
                    "name": "Widget Comp",
                    "component_type": "widget",
                    "order": 0,
                    "html_content": "<div>Widget</div>",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertEqual(comp.component_type, "html")
        self.assertTrue(any("widget" in w for w in warnings))

    def test_valid_types_pass_through(self):
        """Valid types (html, markdown, form, table) are not converted."""
        for comp_type in ("html", "markdown", "form", "table"):
            data = {
                "export_type": "page",
                "page": {"title": "T", "slug": f"valid-{comp_type}"},
                "components": [
                    {
                        "name": f"Comp {comp_type}",
                        "component_type": comp_type,
                        "order": 0,
                        "html_content": "<p/>",
                    },
                ],
            }
            page, warnings = deserialize_page(data)
            comp = page.components.first()
            self.assertEqual(comp.component_type, comp_type)

    def test_google_sheet_type_passes_through_with_resolved_reference(self):
        GoogleSheet.objects.create(
            name="Sponsors Sheet",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
        )
        data = {
            "export_type": "page",
            "page": {"title": "T", "slug": "valid-google-sheet"},
            "components": [
                {
                    "name": "Sheet Comp",
                    "component_type": "google_sheet",
                    "order": 0,
                    "google_sheet_name": "Sponsors Sheet",
                    "google_sheet_style": "bordered",
                },
            ],
        }

        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertEqual(comp.component_type, "google_sheet")
        self.assertIsNotNone(comp.google_sheet)
        self.assertEqual(comp.google_sheet.name, "Sponsors Sheet")
        self.assertEqual(comp.google_sheet_style, "bordered")

    def test_deprecated_type_in_homepage_import(self):
        data = {
            "export_type": "homepage",
            "homepage": {"name": "Old Home"},
            "components": [
                {
                    "name": "Legacy Widget",
                    "component_type": "widget",
                    "order": 0,
                    "html_content": "<p>Old</p>",
                },
            ],
        }
        hp, warnings = deserialize_homepage(data)
        comp = hp.components.first()
        self.assertEqual(comp.component_type, "html")
        self.assertTrue(any("widget" in w for w in warnings))

    def test_unknown_type_converts_to_html(self):
        """Completely unknown types also fall back to html."""
        data = {
            "export_type": "page",
            "page": {"title": "T", "slug": "unknown-type"},
            "components": [
                {
                    "name": "Mystery",
                    "component_type": "carousel",
                    "order": 0,
                    "html_content": "<div/>",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        comp = page.components.first()
        self.assertEqual(comp.component_type, "html")
        self.assertTrue(any("carousel" in w for w in warnings))
