"""Tests for cms app API views: layout."""

from django.core.cache import cache
from django.test import TestCase

from cms.models import CMSPage, FooterContent, Menu, SiteSettings


class LayoutAPIViewTests(TestCase):
    """Tests for the LayoutAPIView (F3 fix)."""

    # noinspection PyMethodMayBeStatic,PyPep8Naming
    def setUp(self):
        cache.clear()

    def test_layout_returns_menus_footer_and_homepage_route(self):
        Menu.objects.create(name="main-nav", display_name="Main Nav")
        FooterContent.objects.create(name="Footer V1", slug="footer-v1", is_active=True)
        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("menus", response.json())
        self.assertIn("footer", response.json())
        self.assertIn("homepage_route", response.json())
        self.assertNotIn("homepage_mode", response.json())

    def test_layout_no_auth_required(self):
        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)

    def test_layout_caches_response(self):
        Menu.objects.create(name="cached-menu", display_name="Cached")
        # First request populates cache
        self.client.get("/layout/")
        # Second request should hit cache (data still returned correctly)
        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(cache.get("layout:data"))

    def test_layout_returns_null_footer_when_none_active(self):
        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["footer"])

    def test_layout_returns_homepage_route_default(self):
        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["homepage_route"], "/")

    def test_layout_returns_selected_homepage_route(self):
        homepage = CMSPage.objects.create(
            slug="home-during-event",
            route="/home-during-event",
            title="During Event Home",
            status="published",
        )
        settings = SiteSettings.load()
        settings.homepage_page = homepage
        settings.save()

        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["homepage_route"], "/home-during-event")

    def test_layout_falls_back_to_root_page_when_selected_page_is_unpublished(self):
        root_page = CMSPage.objects.create(
            slug="home",
            route="/",
            title="Home",
            status="published",
        )
        selected_page = CMSPage.objects.create(
            slug="draft-home",
            route="/draft-home",
            title="Draft Home",
            status="draft",
        )
        settings = SiteSettings.load()
        settings.homepage_page = selected_page
        settings.save()

        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["homepage_route"], root_page.route)
