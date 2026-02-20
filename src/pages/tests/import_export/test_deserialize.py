"""
Tests for import/export deserialization of pages and homepages.

Covers:
- DeserializePageTest: create, update, replace components, missing slug,
  resolve/warn data sources, resolve/warn forms
- DeserializeHomePageTest: create, update, missing name
"""

from django.test import TestCase

from ...admin.content.import_export import (
    deserialize_homepage,
    deserialize_page,
)
from ...models import (
    ComponentDataSource,
    HomePage,
    Page,
    PageComponent,
    PageComponentPlacement,
    UniformForm,
)


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
        old_comp = PageComponent.objects.create(
            name="Old",
            component_type="html",
            html_content="old",
        )
        PageComponentPlacement.objects.create(component=old_comp, page=page, order=0)

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
                    "name": "C",
                    "component_type": "html",
                    "order": 0,
                    "html_content": "<p/>",
                    "data_source_name": "api-source",
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
                    "name": "C",
                    "component_type": "html",
                    "order": 0,
                    "html_content": "<p/>",
                    "data_source_name": "nonexistent",
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
                    "name": "F",
                    "component_type": "form",
                    "order": 0,
                    "html_content": "",
                    "form_slug": "contact",
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
                    "name": "F",
                    "component_type": "form",
                    "order": 0,
                    "html_content": "",
                    "form_slug": "missing-form",
                },
            ],
        }
        page, warnings = deserialize_page(data)
        self.assertTrue(any("missing-form" in w for w in warnings))


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
