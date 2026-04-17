import json

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from authn.models import Member
from cms.models import CMSBlock, CMSPage


class CMSLivePreviewSyncPostingTest(TestCase):
    """Tests for the CMSLivePreviewView POST/GET cache cycle."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = Member.objects.create_user(
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

    def test_post_stores_data_and_returns_200(self):
        """POST to live-preview stores data in cache and returns 200 with ok=True."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "title": "Edited Title",
            "blocks": [
                {"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Edited</p>"}},
            ],
        }
        response = self._post_preview(preview_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        # Verify data is in cache
        cached = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["title"], "Edited Title")
        self.assertEqual(len(cached["blocks"]), 1)

    def test_get_returns_cached_data(self):
        """GET retrieves the data stored by a previous POST."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "title": "Cached Title",
            "blocks": [
                {"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Cached</p>"}},
            ],
        }
        # POST to store
        post_response = self._post_preview(preview_data)
        self.assertEqual(post_response.status_code, 200)

        # GET to retrieve (no auth required for GET)
        self.client.logout()
        get_response = self.client.get(self.live_preview_url)
        self.assertEqual(get_response.status_code, 200)

        data = get_response.json()
        self.assertEqual(data["title"], "Cached Title")
        self.assertEqual(data["blocks"][0]["data"]["body_html"], "<p>Cached</p>")

    def test_post_then_get_full_cycle(self):
        """Full POST -> GET cycle: data posted by staff is retrievable by anonymous GET."""
        self.client.force_login(self.staff)
        preview_data = {
            "slug": "live-preview-test",
            "route": "/live-preview-test",
            "title": "Full Cycle Title",
            "page_css_class": "test-class",
            "meta_description": "Test description",
            "blocks": [
                {"block_type": "rich_text", "sort_order": 0, "data": {"body_html": "<p>Block 1</p>"}},
                {"block_type": "rich_text", "sort_order": 1, "data": {"body_html": "<p>Block 2</p>"}},
            ],
        }
        self._post_preview(preview_data)

        self.client.logout()
        get_response = self.client.get(self.live_preview_url)
        data = get_response.json()

        self.assertEqual(data["title"], "Full Cycle Title")
        self.assertEqual(data["page_css_class"], "test-class")
        self.assertEqual(data["meta_description"], "Test description")
        self.assertEqual(len(data["blocks"]), 2)
        self.assertIn("expires_at", data)

    def test_post_invalid_json_returns_400(self):
        """POST with malformed JSON body returns 400."""
        self.client.force_login(self.staff)
        response = self.client.post(
            self.live_preview_url,
            data="this is not valid json{{{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_post_non_dict_body_returns_400(self):
        """POST with a non-object JSON body (e.g. array) returns 400."""
        self.client.force_login(self.staff)
        response = self.client.post(
            self.live_preview_url,
            data="[1, 2, 3]",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_post_anonymous_is_rejected(self):
        """Anonymous POST to live-preview is rejected (401 unauthenticated or 403 forbidden)."""
        response = self.client.post(
            self.live_preview_url,
            data=json.dumps({"title": "No Auth"}),
            content_type="application/json",
        )
        # DRF returns 401 for unauthenticated requests when DEFAULT_PERMISSION_CLASSES
        # includes IsAuthenticated; IsAdminUser would return 403 for authenticated non-staff.
        self.assertIn(response.status_code, [401, 403])

    def test_post_non_staff_returns_403(self):
        """Authenticated non-staff user POST returns 403."""
        regular_user = Member.objects.create_user(
            password="testpass123",
            is_staff=False,
        )
        self.client.force_login(regular_user)
        response = self.client.post(
            self.live_preview_url,
            data=json.dumps({"title": "Non-Staff"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_post_strips_client_supplied_expires_at(self):
        """Client-supplied expires_at is discarded; server computes its own.

        Defense in depth: a malicious client must not be able to spoof the
        expiry timestamp (e.g. set it to year 2099 to mislead the preview UI).
        The view pops any incoming expires_at before setting its own, so the
        cached value always reflects server time + TTL.
        """
        self.client.force_login(self.staff)
        bogus_expiry = "2099-12-31T23:59:59+00:00"
        self._post_preview({"title": "Spoof Attempt", "expires_at": bogus_expiry, "blocks": []})

        cached = cache.get(f"cms:live-preview:{self.page.pk}")
        self.assertIn("expires_at", cached)
        self.assertNotEqual(cached["expires_at"], bogus_expiry)

        # Server-computed expiry is within the TTL window (10 min).
        from datetime import datetime

        from django.utils import timezone as tz

        expires_at = datetime.fromisoformat(cached["expires_at"])
        diff = (expires_at - tz.now()).total_seconds()
        self.assertGreater(diff, 540)
        self.assertLessEqual(diff, 600)
