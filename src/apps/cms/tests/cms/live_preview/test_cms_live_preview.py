from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.tests.cms.pages.test_cms_views import _make_page
from apps.event.tests.helpers import make_admin, make_superuser


class CMSLivePreviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = make_admin(apps=["cms"], email="cms-live@example.com")
        self.page = _make_page("live", "/live")

    def test_post_requires_staff(self):
        resp = self.client.post(
            f"/cms/live-preview/{self.page.pk}/", '{"title":"Test"}', content_type="application/json"
        )
        self.assertIn(resp.status_code, (401, 403))

    def test_post_non_cms_staff_returns_403(self):
        """Staff scoped to a different app cannot push live-preview data."""
        other = make_admin(apps=["event"], email="event-live@example.com")
        self.client.force_authenticate(other)
        resp = self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            '{"title":"Other"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_post_superuser_stores_data(self):
        self.client.force_authenticate(make_superuser(email="master-live@example.com"))
        resp = self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            '{"title":"Master"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_post_staff_stores_data(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            '{"title":"Preview Title"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_get_returns_cached_preview(self):
        self.client.force_authenticate(self.staff)
        self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            '{"title":"Preview"}',
            content_type="application/json",
        )

        resp = self.client.get(f"/cms/live-preview/{self.page.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Preview")

    def test_get_no_cache_returns_404_for_anonymous(self):
        resp = self.client.get(f"/cms/live-preview/{self.page.pk}/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "Preview not found or expired.")

    def test_get_no_cache_falls_back_to_db_for_staff(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.get(f"/cms/live-preview/{self.page.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "live")

    def test_get_nonexistent_page_returns_404(self):
        import uuid

        resp = self.client.get(f"/cms/live-preview/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)

    def test_post_invalid_json_returns_400(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            "not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class CMSPreviewFetchTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_valid_token_returns_data(self):
        cache.set("cms:preview:test-token-123", {"slug": "preview-page", "title": "Preview"})
        resp = self.client.get("/cms/preview/test-token-123/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "preview-page")

    def test_invalid_token_returns_404(self):
        resp = self.client.get("/cms/preview/nonexistent-token/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())
