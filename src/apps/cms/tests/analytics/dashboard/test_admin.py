"""Tests for the page-view analytics admin: display methods, dashboard stats, geo lookup."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.admin.analytics.page_view.admin import PageViewAdmin
from apps.cms.admin.analytics.page_view.stats import (
    DASHBOARD_CACHE_KEY,
)
from apps.cms.models import PageView

Member = get_user_model()


class PageViewAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = PageViewAdmin(PageView, AdminSite())

    def test_short_referrer_empty(self):
        pv = PageView(path="/x", referrer="")
        self.assertEqual(self.admin.short_referrer(pv), "-")

    def test_short_referrer_short_value_returned_as_is(self):
        pv = PageView(path="/x", referrer="https://short.example.com")
        self.assertEqual(self.admin.short_referrer(pv), "https://short.example.com")

    def test_short_referrer_long_value_truncated(self):
        long_ref = "https://example.com/" + "a" * 80
        pv = PageView(path="/x", referrer=long_ref)
        html = self.admin.short_referrer(pv)
        self.assertIn("&hellip;", html)
        self.assertIn(long_ref[:50], html)
        self.assertIn("title=", html)

    def test_member_display_none(self):
        pv = PageView(path="/x")
        self.assertEqual(self.admin.member_display(pv), "-")

    def test_member_display_with_member_email(self):
        member = Member.objects.create_user(password="pw", first_name="Geo", last_name="User")
        ContactEmail.objects.create(
            member=member,
            email_address="geo-user@example.com",
            email_type="primary",
            verified=True,
        )
        pv = PageView(path="/x", member=member)
        self.assertEqual(self.admin.member_display(pv), "geo-user@example.com")

    def test_member_display_member_without_email_falls_back_to_id(self):
        member = Member.objects.create_user(password="pw", first_name="No", last_name="Email")
        pv = PageView(path="/x", member=member)
        self.assertEqual(self.admin.member_display(pv), str(member.id))

    def test_user_agent_short_empty(self):
        pv = PageView(path="/x", user_agent="")
        self.assertEqual(self.admin.user_agent_short(pv), "-")

    def test_user_agent_short_returns_value(self):
        pv = PageView(path="/x", user_agent="Mozilla/5.0")
        self.assertEqual(self.admin.user_agent_short(pv), "Mozilla/5.0")

    def test_user_agent_short_truncates_long_value(self):
        ua = "Mozilla/5.0 " + "x" * 80
        pv = PageView(path="/x", user_agent=ua)
        html = self.admin.user_agent_short(pv)
        self.assertIn("&hellip;", html)
        self.assertIn(ua[:60], html)

    def test_session_key_short_empty(self):
        pv = PageView(path="/x", session_key="")
        self.assertEqual(self.admin.session_key_short(pv), "-")

    def test_session_key_short_truncates(self):
        pv = PageView(path="/x", session_key="abcdefghijklmnop")
        self.assertEqual(self.admin.session_key_short(pv), "abcdefgh...")

    def test_ip_display_empty(self):
        pv = PageView(path="/x", ip_address=None)
        self.assertEqual(self.admin.ip_display(pv), "-")

    def test_ip_display_renders_link(self):
        pv = PageView(path="/x", ip_address="203.0.113.5")
        html = self.admin.ip_display(pv)
        self.assertIn('data-ip="203.0.113.5"', html)
        self.assertIn("ip-geo-link", html)

    def test_get_urls_includes_geo_lookup_route(self):
        names = [u.name for u in self.admin.get_urls() if u.name]
        self.assertIn("cms_pageview_ip_geo_lookup", names)


class PageViewAdminChangelistTests(TestCase):
    def setUp(self):
        cache.clear()
        PageView.objects.all().delete()
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Analytics",
            last_name="Admin",
        )
        ContactEmail.objects.create(
            member=self.admin_user,
            email_address="analytics-admin@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.login(username="analytics-admin@example.com", password="testpass123")

    def tearDown(self):
        cache.clear()

    def test_changelist_computes_and_caches_dashboard_stats(self):
        PageView.objects.create(path="/home", ip_address="1.1.1.1")
        self.assertIsNone(cache.get(DASHBOARD_CACHE_KEY))

        response = self.client.get(reverse("admin:cms_pageview_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_views"], 1)
        # Stats are cached after first compute.
        self.assertIsNotNone(cache.get(DASHBOARD_CACHE_KEY))

    def test_changelist_uses_cached_stats_without_recomputing(self):
        cache.set(DASHBOARD_CACHE_KEY, {"total_views": 999, "top_pages": [], "last_7_days": []}, 300)

        with patch("apps.cms.admin.analytics.page_view.admin.compute_dashboard_stats") as mock_compute:
            response = self.client.get(reverse("admin:cms_pageview_changelist"))
            mock_compute.assert_not_called()

        self.assertEqual(response.context["total_views"], 999)

    def test_changelist_dashboard_uses_theme_aware_assets(self):
        response = self.client.get(reverse("admin:cms_pageview_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cms/css/pageview-dashboard.css?v=20260608-theme")
        self.assertContains(response, "cms-pageview-dashboard")
        self.assertContains(response, "window.i2gPageViewTheme")
        self.assertContains(response, "theme.register(chart, applyTheme)")
        self.assertNotContains(response, "rgba(255,255,255,0.6)")
        self.assertNotContains(response, "rgba(0,0,0,0.5)")
