import json

from django.core.cache import cache

from apps.cms.tests.cms.live_preview.test_cms_live_preview_sync_posting import _CMSLivePreviewSyncPostingCase


class CMSLivePreviewSyncPostingTest(_CMSLivePreviewSyncPostingCase):
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

    def test_post_oversize_payload_returns_413(self):
        """A payload over the 512 KB limit is rejected before caching."""
        self.client.force_login(self.staff)
        big_block = {"block_type": "rich_text", "data": {"body_html": "x" * 600_000}}
        response = self.client.post(
            self.live_preview_url,
            data=json.dumps({"title": "Big", "blocks": [big_block]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "Preview payload too large.")
        # Nothing was cached for an oversize payload.
        self.assertIsNone(cache.get(f"cms:live-preview:{self.page.pk}"))

    def test_post_non_serializable_payload_returns_400(self):
        """If the payload cannot be JSON-serialized for size checking, return 400."""
        from unittest.mock import patch

        from rest_framework.test import APIRequestFactory, force_authenticate

        from apps.cms.views.cms import CMSLivePreviewView

        factory = APIRequestFactory()
        request = factory.post(self.live_preview_url, {"title": "x"}, format="json")
        force_authenticate(request, user=self.staff)

        with patch("json.dumps", side_effect=TypeError("not serializable")):
            response = CMSLivePreviewView.as_view()(request, page_id=str(self.page.pk))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Payload is not serializable.")
