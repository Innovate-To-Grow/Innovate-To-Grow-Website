"""Tests for cms app API views: layout."""

from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import FooterContent, Menu


class LayoutAPIViewTests(TestCase):
    """Tests for the LayoutAPIView (F3 fix)."""

    # noinspection PyMethodMayBeStatic,PyPep8Naming
    def setUp(self):
        cache.clear()

    def test_layout_returns_only_menus_and_footer(self):
        Menu.objects.create(name="main-nav", display_name="Main Nav")
        FooterContent.objects.create(name="Footer V1", slug="footer-v1", is_active=True)
        response = self.client.get("/layout/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("menus", response.json())
        self.assertIn("footer", response.json())
        self.assertEqual(set(response.json()), {"menus", "footer"})

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
