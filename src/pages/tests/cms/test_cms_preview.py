import json

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member


class CMSPreviewAPITest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = Member.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="testpass123",
            is_staff=True,
        )

    def test_preview_store_requires_staff(self):
        """Anonymous POST to preview store returns 403."""
        response = self.client.post(
            "/admin/pages/cmspage/preview/",
            data=json.dumps({"title": "Test"}),
            content_type="application/json",
        )
        # Redirects to login for anonymous users via admin_view wrapper
        self.assertIn(response.status_code, [302, 403])

    def test_preview_store_returns_token(self):
        """Staff POST returns 200 with token."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "preview",
            "route": "/test",
            "title": "Test",
            "page_css_class": "",
            "meta_description": "",
            "blocks": [{"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Hi</p>"}}],
        }
        response = self.client.post(
            "/admin/pages/cmspage/preview/",
            data=json.dumps(preview_data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        self.assertTrue(len(data["token"]) > 0)

    def test_preview_fetch_returns_data(self):
        """GET with valid token returns cached data."""
        preview_data = {"slug": "preview", "title": "Test Page", "blocks": []}
        cache.set("cms:preview:test-token-123", preview_data, timeout=600)

        response = self.client.get("/cms/preview/test-token-123/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Test Page")

    def test_preview_fetch_expired_returns_404(self):
        """GET with invalid/expired token returns 404."""
        response = self.client.get("/cms/preview/nonexistent-token/")
        self.assertEqual(response.status_code, 404)
