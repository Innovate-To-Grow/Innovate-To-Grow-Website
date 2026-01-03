from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ..models import HomePage, Menu, Page


class HomePageAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("pages:home-page")

    def test_get_active_home_page(self):
        HomePage.objects.create(name="Active", is_active=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Active")

    def test_no_active_home_page(self):
        HomePage.objects.create(name="Inactive", is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PageRetrieveAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.page = Page.objects.create(title="About", slug="about")

    def test_retrieve_page(self):
        url = reverse("pages:page-retrieve", kwargs={"slug": "about"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "About")

    def test_retrieve_not_found(self):
        url = reverse("pages:page-retrieve", kwargs={"slug": "missing"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MenuAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.menu = Menu.objects.create(name="main", display_name="Main Menu")

    def test_list_menus(self):
        url = reverse("pages:menu-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["menus"]), 1)
        self.assertEqual(response.data["menus"][0]["name"], "main")
