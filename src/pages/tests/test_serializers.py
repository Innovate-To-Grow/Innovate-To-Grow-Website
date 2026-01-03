from django.test import TestCase

from ..models import HomePage, Menu, MenuPageLink, Page, PageComponent
from ..serializers import HomePageSerializer, MenuSerializer, PageSerializer


class PageSerializerTest(TestCase):
    def test_serialize_page(self):
        page = Page.objects.create(title="Test", slug="test")
        PageComponent.objects.create(page=page, component_type="html", order=1, html_content="<p>Body</p>")

        serializer = PageSerializer(page)
        data = serializer.data
        self.assertEqual(data["title"], "Test")
        self.assertEqual(data["slug"], "test")
        self.assertEqual(len(data["components"]), 1)
        self.assertEqual(data["components"][0]["html_content"], "<p>Body</p>")


class MenuSerializerTest(TestCase):
    def test_serialize_menu_with_links(self):
        menu = Menu.objects.create(name="main", display_name="Main")
        page = Page.objects.create(title="Home", slug="home")
        MenuPageLink.objects.create(menu=menu, page=page, order=1)

        serializer = MenuSerializer(menu)
        data = serializer.data
        self.assertEqual(data["name"], "main")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["title"], "Home")
        self.assertEqual(data["items"][0]["url"], "/pages/home")


class HomePageSerializerTest(TestCase):
    def test_serialize_homepage(self):
        hp = HomePage.objects.create(name="Home V1", is_active=True)
        PageComponent.objects.create(home_page=hp, component_type="html", order=1, html_content="<h1>Welcome</h1>")

        serializer = HomePageSerializer(hp)
        data = serializer.data
        self.assertEqual(data["name"], "Home V1")
        self.assertTrue(data["is_active"])
        self.assertEqual(len(data["components"]), 1)
