from django.test import TestCase

from ..models import HomePage, Menu, Page, PageComponent
from ..serializers import HomePageSerializer, MenuSerializer, PageComponentSerializer, PageSerializer


class PageSerializerTest(TestCase):
    def test_serialize_page(self):
        page = Page.objects.create(title="Test", slug="test")
        PageComponent.objects.create(
            name="Body", page=page, component_type="html", order=1, html_content="<p>Body</p>"
        )

        serializer = PageSerializer(page)
        data = serializer.data
        self.assertEqual(data["title"], "Test")
        self.assertEqual(data["slug"], "test")
        self.assertEqual(len(data["components"]), 1)
        self.assertEqual(data["components"][0]["html_content"], "<p>Body</p>")

    def test_serialize_page_includes_status(self):
        """PageSerializer includes status and published fields."""
        page = Page.objects.create(title="Draft Page", slug="draft-page")
        serializer = PageSerializer(page)
        data = serializer.data
        self.assertEqual(data["status"], "draft")
        self.assertFalse(data["published"])

    def test_serialize_published_page(self):
        """Published page has published=True in serialized output."""
        page = Page.objects.create(title="Pub Page", slug="pub-page", status="published")
        serializer = PageSerializer(page)
        data = serializer.data
        self.assertEqual(data["status"], "published")
        self.assertTrue(data["published"])

    def test_serialize_page_status_is_readonly(self):
        """Published field is read-only in serializer."""
        serializer = PageSerializer()
        self.assertTrue(serializer.fields["published"].read_only)


class MenuSerializerTest(TestCase):
    def test_serialize_menu_with_page_items(self):
        """Menu with JSON page items serializes correctly."""
        page = Page.objects.create(title="About", slug="about")
        menu = Menu.objects.create(
            name="main",
            display_name="Main",
            items=[
                {
                    "type": "page",
                    "title": "About Us",
                    "page_slug": "about",
                    "icon": "",
                    "open_in_new_tab": False,
                    "children": [],
                }
            ],
        )

        serializer = MenuSerializer(menu)
        data = serializer.data
        self.assertEqual(data["name"], "main")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["title"], "About Us")
        self.assertEqual(data["items"][0]["url"], "/pages/about")
        self.assertEqual(data["items"][0]["page_type"], "page")

    def test_serialize_menu_with_home_item(self):
        """Menu with home type item serializes correctly."""
        menu = Menu.objects.create(
            name="nav",
            display_name="Nav",
            items=[
                {
                    "type": "home",
                    "title": "Home",
                    "icon": "",
                    "open_in_new_tab": False,
                    "children": [],
                }
            ],
        )

        serializer = MenuSerializer(menu)
        data = serializer.data
        self.assertEqual(data["items"][0]["url"], "/")
        self.assertEqual(data["items"][0]["page_type"], "home")

    def test_serialize_menu_with_external_item(self):
        """Menu with external URL item serializes correctly."""
        menu = Menu.objects.create(
            name="links",
            display_name="Links",
            items=[
                {
                    "type": "external",
                    "title": "Google",
                    "url": "https://google.com",
                    "icon": "",
                    "open_in_new_tab": True,
                    "children": [],
                }
            ],
        )

        serializer = MenuSerializer(menu)
        data = serializer.data
        self.assertEqual(data["items"][0]["title"], "Google")
        self.assertEqual(data["items"][0]["url"], "https://google.com")
        self.assertTrue(data["items"][0]["open_in_new_tab"])


class HomePageSerializerTest(TestCase):
    def test_serialize_homepage(self):
        """Serialize a published and active home page."""
        hp = HomePage.objects.create(name="Home V1", status="published", is_active=True)
        PageComponent.objects.create(
            name="Welcome", home_page=hp, component_type="html", order=1, html_content="<h1>Welcome</h1>"
        )

        serializer = HomePageSerializer(hp)
        data = serializer.data
        self.assertEqual(data["name"], "Home V1")
        self.assertTrue(data["is_active"])
        self.assertEqual(len(data["components"]), 1)

    def test_serialize_homepage_includes_status(self):
        """HomePageSerializer includes status and published fields."""
        hp = HomePage.objects.create(name="Draft Home")
        serializer = HomePageSerializer(hp)
        data = serializer.data
        self.assertEqual(data["status"], "draft")
        self.assertFalse(data["published"])

    def test_serialize_published_homepage(self):
        """Published home page has published=True."""
        hp = HomePage.objects.create(name="Published Home", status="published", is_active=True)
        serializer = HomePageSerializer(hp)
        data = serializer.data
        self.assertEqual(data["status"], "published")
        self.assertTrue(data["published"])


class PageComponentSerializerFieldsTest(TestCase):
    """Test that PageComponentSerializer includes name and is_enabled."""

    def test_serializer_includes_name(self):
        page = Page.objects.create(title="T", slug="ser-name")
        comp = PageComponent.objects.create(
            page=page, name="My Component", component_type="html",
            order=1, html_content="<p/>",
        )
        serializer = PageComponentSerializer(comp)
        self.assertIn("name", serializer.data)
        self.assertEqual(serializer.data["name"], "My Component")

    def test_serializer_includes_is_enabled(self):
        page = Page.objects.create(title="T", slug="ser-enabled")
        comp = PageComponent.objects.create(
            page=page, name="C", component_type="html",
            order=1, is_enabled=False, html_content="<p/>",
        )
        serializer = PageComponentSerializer(comp)
        self.assertIn("is_enabled", serializer.data)
        self.assertFalse(serializer.data["is_enabled"])

    def test_name_via_page_serializer(self):
        """name and is_enabled appear in nested output via PageSerializer."""
        page = Page.objects.create(title="T", slug="ser-nested")
        PageComponent.objects.create(
            page=page, name="Hero Section", component_type="html",
            order=1, is_enabled=True, html_content="<h1>Hi</h1>",
        )
        serializer = PageSerializer(page)
        comp_data = serializer.data["components"][0]
        self.assertEqual(comp_data["name"], "Hero Section")
        self.assertTrue(comp_data["is_enabled"])

    def test_name_via_homepage_serializer(self):
        """name and is_enabled appear in nested output via HomePageSerializer."""
        hp = HomePage.objects.create(name="Home Ser")
        PageComponent.objects.create(
            home_page=hp, name="Welcome", component_type="html",
            order=1, is_enabled=True, html_content="<h1>Welcome</h1>",
        )
        serializer = HomePageSerializer(hp)
        comp_data = serializer.data["components"][0]
        self.assertEqual(comp_data["name"], "Welcome")
        self.assertTrue(comp_data["is_enabled"])
