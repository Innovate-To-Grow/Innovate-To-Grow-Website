"""Tests for sheets app API views: sheets data and sheets refresh."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from sheets.models import GoogleSheetSource
from sheets.services import GoogleSheetsConfigError

Member = get_user_model()


class SheetsDataViewTests(TestCase):
    """Tests for the SheetsDataView."""

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

    @patch("sheets.views.fetch_source_data")
    def test_returns_data_for_active_source(self, mock_fetch):
        mock_fetch.return_value = {"slug": "test-sheet", "rows": []}
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "test-sheet")

    @patch("sheets.views.fetch_source_data")
    def test_returns_502_on_config_error(self, mock_fetch):
        mock_fetch.side_effect = GoogleSheetsConfigError("Not configured")
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 502)

    @patch("sheets.views.fetch_source_data")
    def test_returns_502_on_unexpected_exception(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("Something broke")
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 502)

    @patch("sheets.views.fetch_source_data")
    def test_no_auth_required(self, mock_fetch):
        mock_fetch.return_value = {"slug": "test-sheet", "rows": []}
        # No authentication — should still succeed
        response = self.client.get("/sheets/test-sheet/")
        self.assertEqual(response.status_code, 200)


class SheetsRefreshViewTests(TestCase):
    """Tests for the SheetsRefreshView."""

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

    @patch("sheets.views.fetch_source_data")
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
