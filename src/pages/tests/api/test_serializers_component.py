from django.test import TestCase

from ...models import GoogleSheet, HomePage, Page, PageComponent
from ...serializers import HomePageSerializer, PageComponentSerializer, PageSerializer


class PageComponentSerializerFieldsTest(TestCase):
    """Test that PageComponentSerializer includes name and is_enabled."""

    def test_serializer_includes_name(self):
        page = Page.objects.create(title="T", slug="ser-name")
        comp = PageComponent.objects.create(
            page=page,
            name="My Component",
            component_type="html",
            order=1,
            html_content="<p/>",
        )
        serializer = PageComponentSerializer(comp)
        self.assertIn("name", serializer.data)
        self.assertEqual(serializer.data["name"], "My Component")

    def test_serializer_includes_is_enabled(self):
        page = Page.objects.create(title="T", slug="ser-enabled")
        comp = PageComponent.objects.create(
            page=page,
            name="C",
            component_type="html",
            order=1,
            is_enabled=False,
            html_content="<p/>",
        )
        serializer = PageComponentSerializer(comp)
        self.assertIn("is_enabled", serializer.data)
        self.assertFalse(serializer.data["is_enabled"])

    def test_name_via_page_serializer(self):
        """name and is_enabled appear in nested output via PageSerializer."""
        page = Page.objects.create(title="T", slug="ser-nested")
        PageComponent.objects.create(
            page=page,
            name="Hero Section",
            component_type="html",
            order=1,
            is_enabled=True,
            html_content="<h1>Hi</h1>",
        )
        serializer = PageSerializer(page)
        comp_data = serializer.data["components"][0]
        self.assertEqual(comp_data["name"], "Hero Section")
        self.assertTrue(comp_data["is_enabled"])

    def test_name_via_homepage_serializer(self):
        """name and is_enabled appear in nested output via HomePageSerializer."""
        hp = HomePage.objects.create(name="Home Ser")
        PageComponent.objects.create(
            home_page=hp,
            name="Welcome",
            component_type="html",
            order=1,
            is_enabled=True,
            html_content="<h1>Welcome</h1>",
        )
        serializer = HomePageSerializer(hp)
        comp_data = serializer.data["components"][0]
        self.assertEqual(comp_data["name"], "Welcome")
        self.assertTrue(comp_data["is_enabled"])

    def test_serializer_includes_google_sheet_fields(self):
        page = Page.objects.create(title="T", slug="ser-google-sheet")
        google_sheet = GoogleSheet.objects.create(
            name="Sponsors",
            spreadsheet_id="sheet-id",
            sheet_name="Sheet1",
        )
        comp = PageComponent.objects.create(
            page=page,
            name="Sponsors Table",
            component_type="google_sheet",
            google_sheet=google_sheet,
            google_sheet_style="striped",
        )
        serializer = PageComponentSerializer(comp)
        self.assertEqual(str(serializer.data["google_sheet"]), str(google_sheet.id))
        self.assertEqual(serializer.data["google_sheet_style"], "striped")

    def test_google_sheet_fields_present_in_nested_page_serializer(self):
        page = Page.objects.create(title="T", slug="ser-google-nested")
        google_sheet = GoogleSheet.objects.create(
            name="Schedule",
            spreadsheet_id="sheet-id",
            sheet_name="Sheet1",
        )
        PageComponent.objects.create(
            page=page,
            name="Schedule Table",
            component_type="google_sheet",
            google_sheet=google_sheet,
            google_sheet_style="compact",
        )

        serializer = PageSerializer(page)
        comp_data = serializer.data["components"][0]
        self.assertEqual(str(comp_data["google_sheet"]), str(google_sheet.id))
        self.assertEqual(comp_data["google_sheet_style"], "compact")
