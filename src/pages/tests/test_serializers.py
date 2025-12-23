from django.test import TestCase
from ..models import Page, Menu, MenuPageLink, HomePage
from ..serializers import (
    PageSerializer, MenuSerializer, 
    MenuPageLinkSerializer, HomePageSerializer
)


class PageSerializerTest(TestCase):
    def test_serialize_page(self):
        page = Page.objects.create(title="Test", slug="test", page_body="<p>Body</p>")
        serializer = PageSerializer(page)
        data = serializer.data
        self.assertEqual(data['title'], "Test")
        self.assertEqual(data['slug'], "test")
        self.assertEqual(data['page_body'], "<p>Body</p>")
        self.assertEqual(data['page_type'], "page")


class MenuSerializerTest(TestCase):
    def test_serialize_menu_with_links(self):
        menu = Menu.objects.create(name="main", display_name="Main")
        page = Page.objects.create(title="Home", slug="home")
        MenuPageLink.objects.create(menu=menu, page=page, order=1)
        
        serializer = MenuSerializer(menu)
        data = serializer.data
        self.assertEqual(data['name'], "main")
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['title'], "Home")
        self.assertEqual(data['items'][0]['url'], "/pages/home")


class HomePageSerializerTest(TestCase):
    def test_serialize_homepage(self):
        hp = HomePage.objects.create(name="Home V1", body="<h1>Welcome</h1>", is_active=True)
        serializer = HomePageSerializer(hp)
        data = serializer.data
        self.assertEqual(data['name'], "Home V1")
        self.assertEqual(data['body'], "<h1>Welcome</h1>")
        self.assertTrue(data['is_active'])
