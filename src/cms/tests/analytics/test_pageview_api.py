"""Tests for PageViewCreateView: IP extraction, serializer validation, auth."""

from django.test import TestCase
from rest_framework.test import APIClient

from cms.models import PageView
from cms.services.analytics import flush_sync


class PageViewIPExtractionTests(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()
        self.client = APIClient()

    def test_ip_from_x_forwarded_for(self):
        self.client.post(
            "/analytics/pageview/",
            {"path": "/test"},
            format="json",
            HTTP_X_FORWARDED_FOR="203.0.113.50, 70.41.3.18",
        )
        flush_sync()
        pv = PageView.objects.first()
        self.assertEqual(pv.ip_address, "203.0.113.50")

    def test_ip_from_remote_addr_fallback(self):
        self.client.post(
            "/analytics/pageview/",
            {"path": "/test"},
            format="json",
        )
        flush_sync()
        pv = PageView.objects.first()
        # Django test client uses 127.0.0.1
        self.assertEqual(pv.ip_address, "127.0.0.1")

    def test_user_agent_captured(self):
        self.client.post(
            "/analytics/pageview/",
            {"path": "/test"},
            format="json",
            HTTP_USER_AGENT="TestBot/1.0",
        )
        flush_sync()
        pv = PageView.objects.first()
        self.assertEqual(pv.user_agent, "TestBot/1.0")


class PageViewValidationTests(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()
        self.client = APIClient()

    def test_missing_path_returns_400(self):
        resp = self.client.post("/analytics/pageview/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_empty_path_returns_400(self):
        resp = self.client.post("/analytics/pageview/", {"path": ""}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_referrer_optional(self):
        resp = self.client.post("/analytics/pageview/", {"path": "/"}, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_extra_fields_ignored(self):
        resp = self.client.post("/analytics/pageview/", {"path": "/", "extra": "data"}, format="json")
        self.assertEqual(resp.status_code, 201)


class PageViewAuthTests(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()
        self.client = APIClient()

    def test_anonymous_can_create(self):
        resp = self.client.post("/analytics/pageview/", {"path": "/"}, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_authenticated_user_recorded(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="viewer", password="pass")
        self.client.force_authenticate(user)
        self.client.post("/analytics/pageview/", {"path": "/about"}, format="json")

        flush_sync()
        pv = PageView.objects.first()
        self.assertEqual(pv.member, user)

    def test_anonymous_member_is_null(self):
        self.client.post("/analytics/pageview/", {"path": "/about"}, format="json")

        flush_sync()
        pv = PageView.objects.first()
        self.assertIsNone(pv.member)
