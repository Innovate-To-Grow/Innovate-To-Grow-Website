"""
Tests for import/export serialization and file collection utilities.

Covers:
- SerializePageTest: page serialization with and without file paths
- SerializeHomePageTest: homepage serialization
- CollectComponentFilesTest: collect_component_files helper
"""

from django.core.files.base import ContentFile
from django.test import TestCase

from ...admin.content.import_export import (
    collect_component_files,
    serialize_homepage,
    serialize_page,
)
from ...models import (
    ComponentDataSource,
    GoogleSheet,
    HomePage,
    Page,
    PageComponent,
    PageComponentImage,
    UniformForm,
)


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
            page=page,
            name="Hero",
            component_type="html",
            order=0,
            html_content="<h1>Hello</h1>",
            css_code="h1 { color: red; }",
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
            page=page,
            name="C",
            component_type="html",
            order=0,
            html_content="<p>x</p>",
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
            page=page,
            name="C",
            component_type="html",
            order=0,
            html_content="<p>x</p>",
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
            page=page,
            name="Gallery",
            component_type="html",
            order=0,
            html_content="<div/>",
        )
        PageComponentImage.objects.create(
            component=comp,
            order=0,
            alt="Photo 1",
            caption="Cap 1",
        )
        data = serialize_page(page)
        images = data["components"][0]["images"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["alt"], "Photo 1")

    def test_data_source_ref_serialized(self):
        ds = ComponentDataSource.objects.create(
            source_name="my-api",
            source_url="/api/data/",
        )
        page = Page.objects.create(title="T", slug="t")
        PageComponent.objects.create(
            page=page,
            name="Dynamic",
            component_type="html",
            order=0,
            html_content="<p>d</p>",
            data_source=ds,
        )
        data = serialize_page(page)
        self.assertEqual(data["components"][0]["data_source_name"], "my-api")

    def test_form_ref_serialized(self):
        form = UniformForm.objects.create(name="Contact", slug="contact")
        page = Page.objects.create(title="T", slug="t")
        PageComponent.objects.create(
            page=page,
            name="Form",
            component_type="form",
            order=0,
            html_content="",
            form=form,
        )
        data = serialize_page(page)
        self.assertEqual(data["components"][0]["form_slug"], "contact")

    def test_google_sheet_ref_serialized(self):
        google_sheet = GoogleSheet.objects.create(
            name="Event Schedule",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
        )
        page = Page.objects.create(title="T", slug="google-sheet-serialized")
        PageComponent.objects.create(
            page=page,
            name="Schedule",
            component_type="google_sheet",
            order=0,
            google_sheet=google_sheet,
            google_sheet_style="striped",
        )
        data = serialize_page(page)
        self.assertEqual(data["components"][0]["google_sheet_name"], "Event Schedule")
        self.assertEqual(data["components"][0]["google_sheet_style"], "striped")


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
            home_page=hp,
            name="Welcome",
            component_type="html",
            order=0,
            html_content="<h1>Welcome</h1>",
        )
        data = serialize_homepage(hp)
        self.assertEqual(len(data["components"]), 1)


class CollectComponentFilesTest(TestCase):
    def test_collects_all_file_paths(self):
        page = Page.objects.create(title="T", slug="collect-test")
        comp = PageComponent.objects.create(
            page=page,
            name="C",
            component_type="html",
            order=0,
            html_content="<p/>",
        )
        # Save files
        comp.image.save("hero.png", ContentFile(b"IMG"), save=False)
        comp.css_file.save("style.css", ContentFile(b"CSS"), save=False)
        PageComponent.objects.filter(pk=comp.pk).update(
            image=comp.image.name,
            css_file=comp.css_file.name,
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
