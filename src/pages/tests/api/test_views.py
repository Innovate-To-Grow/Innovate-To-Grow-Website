"""Tests for pages app API views: layout, sheets data, and sheets refresh."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from pages.models import CMSPage, FooterContent, GoogleSheetSource, Menu, SiteSettings
from pages.services.google_sheets import GoogleSheetsConfigError

Member = get_user_model()


class LayoutAPIViewTests(TestCase):
    """Tests for the LayoutAPIView (F3 fix)."""

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


class SheetsDataViewTests(TestCase):
    """Tests for the SheetsDataView (B8 fix)."""

    def setUp(self):
        cache.clear()
        self.source = GoogleSheetSource.objects.create(
            slug="test-sheet",
            title="Test Sheet",
            sheet_type="current-event",
            spreadsheet_id="fake-id",
            range_a1="A1:Z100",
            is_active=True,
        )

    def test_returns_404_for_unknown_slug(self):
        response = self.client.get("/sheets/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_returns_404_for_inactive_source(self):
        self.source.is_active = False
        self.source.save()
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 404)

    @patch("pages.views.sheets.fetch_source_data")
    def test_returns_data_for_active_source(self, mock_fetch):
        mock_fetch.return_value = {"slug": "test-sheet", "rows": []}
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "test-sheet")

    @patch("pages.views.sheets.fetch_source_data")
    def test_returns_502_on_config_error(self, mock_fetch):
        mock_fetch.side_effect = GoogleSheetsConfigError("Not configured")
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 502)

    @patch("pages.views.sheets.fetch_source_data")
    def test_returns_502_on_unexpected_exception(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("Something broke")
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 502)

    @patch("pages.views.sheets.fetch_source_data")
    def test_no_auth_required(self, mock_fetch):
        mock_fetch.return_value = {"slug": "test-sheet", "rows": []}
        # No authentication — should still succeed
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 200)


class SheetsRefreshViewTests(TestCase):
    """Tests for the SheetsRefreshView (B8 fix)."""

    def setUp(self):
        cache.clear()
        self.admin_user = Member.objects.create_superuser(
            username="sheets-admin",
            email="sheets-admin@example.com",
            password="testpass123",
        )
        self.source = GoogleSheetSource.objects.create(
            slug="refresh-sheet",
            title="Refresh Sheet",
            sheet_type="current-event",
            spreadsheet_id="fake-id",
            range_a1="A1:Z100",
            is_active=True,
        )

    def test_refresh_requires_admin(self):
        # Non-admin user
        regular = Member.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123",
            is_active=True,
        )
        self.client.force_login(regular)
        response = self.client.post("/sheets/refresh-sheet/refresh/")
        self.assertEqual(response.status_code, 403)

    @patch("pages.views.sheets.fetch_source_data")
    def test_refresh_clears_cache_and_returns_fresh_data(self, mock_fetch):
        # Pre-populate cache
        cache.set("sheets:refresh-sheet:data", {"old": True})
        cache.set("sheets:refresh-sheet:stale", {"old": True})
        cache.set("layout:data", {"old": True})

        def fake_fetch(source):
            self.assertIsNone(cache.get("sheets:refresh-sheet:data"))
            self.assertIsNone(cache.get("sheets:refresh-sheet:stale"))
            self.assertIsNone(cache.get("layout:data"))
            return {"slug": "refresh-sheet", "rows": [], "fresh": True}

        mock_fetch.side_effect = fake_fetch

        self.client.force_login(self.admin_user)
        response = self.client.post("/sheets/refresh-sheet/refresh/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["fresh"])

    def test_refresh_returns_404_for_unknown_slug(self):
        self.client.force_login(self.admin_user)
        response = self.client.post("/sheets/nonexistent/refresh/")
        self.assertEqual(response.status_code, 404)
