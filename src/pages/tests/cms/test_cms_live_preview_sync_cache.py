import json

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member
from pages.models import CMSBlock, CMSPage


class CMSLivePreviewSyncCacheTest(TestCase):
    """Tests for the CMSLivePreviewView POST/GET cache cycle."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = Member.objects.create_user(
            username="livepreview_staff",
            email="livepreview@test.com",
            password="testpass123",
            is_staff=True,
        )
        self.page = CMSPage.objects.create(
            slug="live-preview-test",
            route="/live-preview-test",
            title="Live Preview Test",
            status="published",
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Original content from DB</p>"},
        )
        self.live_preview_url = f"/cms/live-preview/{self.page.pk}/"

    def _post_preview(self, data, authenticate=True):
        """Helper to POST live preview data."""
        if authenticate:
            self.client.force_login(self.staff)
        return self.client.post(
            self.live_preview_url,
            data=json.dumps(data),
            content_type="application/json",
        )

    # --- 1. POST stores data in cache and returns 200 ---

    def test_get_falls_back_to_database(self):
        """GET returns serialized DB data when cache is empty."""
        # Cache is cleared in setUp, so no cached data exists
        response = self.client.get(self.live_preview_url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["slug"], "live-preview-test")
        self.assertEqual(data["title"], "Live Preview Test")
        self.assertEqual(len(data["blocks"]), 1)
        self.assertEqual(data["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(data["blocks"][0]["data"]["body_html"], "<p>Original content from DB</p>")

    def test_get_nonexistent_page_returns_404(self):
        """GET with a UUID that has no cache and no DB record returns 404."""
        import uuid

        fake_uuid = uuid.uuid4()
        response = self.client.get(f"/cms/live-preview/{fake_uuid}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Page not found.")

    def test_get_prefers_cache_over_database(self):
        """GET returns cached data even when DB has different data."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "title": "Cached Version (Different from DB)",
            "blocks": [],
        }
        self._post_preview(preview_data)

        self.client.logout()
        response = self.client.get(self.live_preview_url)
        data = response.json()
        # Should return cached data, not DB data
        self.assertEqual(data["title"], "Cached Version (Different from DB)")
        self.assertNotEqual(data["title"], "Live Preview Test")

    def test_post_adds_expires_at_field(self):
        """POST adds an expires_at ISO timestamp to the cached data."""
        self.client.force_login(self.staff)
        preview_data = {"title": "TTL Test", "blocks": []}
        self._post_preview(preview_data)

        cached = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertIn("expires_at", cached)

        # Verify expires_at is a valid ISO timestamp roughly 10 minutes from now
        from datetime import datetime

        from django.utils import timezone as tz

        expires_at = datetime.fromisoformat(cached["expires_at"])
        now = tz.now()
        # expires_at should be between 9 and 11 minutes from now
        diff = (expires_at - now).total_seconds()
        self.assertGreater(diff, 540)  # at least 9 minutes
        self.assertLessEqual(diff, 600)  # at most 10 minutes

    def test_successive_posts_update_cache(self):
        """Multiple POSTs overwrite the cache with the latest data."""
        self.client.force_login(self.staff)

        # First POST
        self._post_preview({"title": "Version 1", "blocks": []})
        cached_v1 = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertEqual(cached_v1["title"], "Version 1")

        # Second POST
        self._post_preview(
            {
                "title": "Version 2",
                "blocks": [{"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>New</p>"}}],
            }
        )
        cached_v2 = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertEqual(cached_v2["title"], "Version 2")
        self.assertEqual(len(cached_v2["blocks"]), 1)

        # GET should return Version 2
        self.client.logout()
        response = self.client.get(self.live_preview_url)
        self.assertEqual(response.json()["title"], "Version 2")

    def test_get_allows_anonymous_access(self):
        """GET endpoint is accessible without authentication."""
        # Seed cache
        cache.set(f"cms:live-preview:{self.page.pk}", {"title": "Public", "blocks": []}, timeout=600)

        # No login
        response = self.client.get(self.live_preview_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Public")
