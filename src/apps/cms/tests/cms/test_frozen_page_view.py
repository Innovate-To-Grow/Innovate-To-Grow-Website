"""Tests for the frozen-page document serving view (headers + access control)."""

import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.cms.models import FrozenPage

User = get_user_model()


def _make_user(name, **flags):
    return User.objects.create_user(
        email=f"{name}@example.com",
        password="pw",
        first_name=name.title(),
        last_name="Test",
        **flags,
    )


class FrozenPageDocumentViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.published = FrozenPage.objects.create(
            source_url="https://example.com/",
            slug="published-page",
            status="published",
            frozen_html="<!DOCTYPE html><html><body>FROZEN</body></html>",
        )
        self.draft = FrozenPage.objects.create(
            source_url="https://example.com/draft",
            slug="draft-page",
            status="draft",
            frozen_html="<!DOCTYPE html><html><body>DRAFT</body></html>",
        )

    def test_published_served_with_security_headers(self):
        resp = self.client.get(reverse("cms-frozen-page", args=[self.published.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/html; charset=utf-8")
        csp = resp["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("style-src 'unsafe-inline' data:", csp)
        self.assertIn("frame-ancestors 'self'", csp)
        # X-Frame-Options must be absent so cross-origin frame-ancestors governs framing.
        self.assertNotIn("X-Frame-Options", resp)
        self.assertEqual(resp["Referrer-Policy"], "no-referrer")
        self.assertIn(b"FROZEN", resp.content)

    def test_csp_includes_configured_frontend_origin(self):
        with self.settings(FRONTEND_URL="https://frontend.example/"):
            resp = self.client.get(reverse("cms-frozen-page", args=[self.published.pk]))
        self.assertIn("frame-ancestors 'self' https://frontend.example", resp["Content-Security-Policy"])

    def test_unknown_returns_404(self):
        resp = self.client.get(reverse("cms-frozen-page", args=[uuid.uuid4()]))
        self.assertEqual(resp.status_code, 404)

    def test_draft_anonymous_returns_404(self):
        resp = self.client.get(reverse("cms-frozen-page", args=[self.draft.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_draft_visible_to_staff(self):
        self.client.force_login(_make_user("staff", is_staff=True))
        resp = self.client.get(reverse("cms-frozen-page", args=[self.draft.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"DRAFT", resp.content)

    def test_draft_hidden_from_non_staff_user(self):
        self.client.force_login(_make_user("member"))
        resp = self.client.get(reverse("cms-frozen-page", args=[self.draft.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_published_response_is_cached(self):
        url = reverse("cms-frozen-page", args=[self.published.pk])
        self.client.get(url)  # populates cache
        # Direct UPDATE bypasses cache invalidation; cached body should still be served.
        FrozenPage.objects.filter(pk=self.published.pk).update(frozen_html="<html>NEW</html>")
        resp = self.client.get(url)
        self.assertIn(b"FROZEN", resp.content)
        self.assertNotIn(b"NEW", resp.content)
