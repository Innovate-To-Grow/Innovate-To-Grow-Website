from django.test import TestCase

from ...models import HomePage, Menu, Page
from ...serializers import HomePageSerializer, MenuSerializer, PageSerializer


class PageSerializerTest(TestCase):
    def test_serialize_page_with_html_css(self):
        page = Page.objects.create(
            title="Test",
            slug="test",
            html="<p>Body</p>",
            css="p { color: red; }",
        )

        serializer = PageSerializer(page)
        data = serializer.data
        self.assertEqual(data["title"], "Test")
        self.assertEqual(data["slug"], "test")
        self.assertEqual(data["html"], "<p>Body</p>")
        self.assertEqual(data["css"], "p { color: red; }")

    def test_serialize_page_includes_dynamic_config(self):
        page = Page.objects.create(
            title="Dynamic",
            slug="dynamic",
            dynamic_config={"sources": [{"name": "events", "url": "/api/events/"}]},
        )
        serializer = PageSerializer(page)
        data = serializer.data
        self.assertEqual(data["dynamic_config"]["sources"][0]["name"], "events")

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
    def test_serialize_homepage_with_html_css(self):
        """Serialize a published and active home page with html/css fields."""
        hp = HomePage.objects.create(
            name="Home V1",
            status="published",
            is_active=True,
            html="<h1>Welcome</h1>",
            css="h1 { color: blue; }",
        )

        serializer = HomePageSerializer(hp)
        data = serializer.data
        self.assertEqual(data["name"], "Home V1")
        self.assertTrue(data["is_active"])
        self.assertEqual(data["html"], "<h1>Welcome</h1>")
        self.assertEqual(data["css"], "h1 { color: blue; }")

    def test_serialize_homepage_includes_dynamic_config(self):
        hp = HomePage.objects.create(
            name="Dynamic Home",
            dynamic_config={"banner": {"enabled": True}},
        )
        serializer = HomePageSerializer(hp)
        data = serializer.data
        self.assertEqual(data["dynamic_config"]["banner"]["enabled"], True)

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
