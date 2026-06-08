"""Tests for the page-view analytics admin: display methods, dashboard stats, geo lookup."""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.cms.admin.analytics.page_view.admin import PageViewAdmin
from apps.cms.admin.analytics.page_view.geo import IP_GEO_CACHE_PREFIX, ip_geo_lookup_view
from apps.cms.admin.analytics.page_view.stats import (
    DASHBOARD_CACHE_KEY,
    compute_dashboard_stats,
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


class ComputeDashboardStatsTests(TestCase):
    def setUp(self):
        PageView.objects.all().delete()

    def test_empty_dataset_defaults(self):
        stats = compute_dashboard_stats()
        self.assertEqual(stats["total_views"], 0)
        self.assertEqual(stats["today_views"], 0)
        self.assertEqual(stats["unique_paths"], 0)
        self.assertEqual(stats["unique_visitors"], 0)
        self.assertEqual(stats["top_pages"], [])
        self.assertEqual(stats["top_referrers"], [])
        self.assertEqual(len(stats["last_7_days"]), 7)
        self.assertEqual(len(stats["hourly_views"]), 24)
        # max_daily_count defaults to 1 to avoid divide-by-zero in charts.
        self.assertEqual(stats["max_daily_count"], 1)
        self.assertEqual(stats["week_views"], 0)
        self.assertEqual(stats["avg_daily_views"], 0.0)

    def test_populated_dataset_aggregates(self):
        now = timezone.now()
        # Two views today on /home from same IP, one on /about from another IP.
        PageView.objects.create(path="/home", ip_address="1.1.1.1", referrer="https://google.com")
        PageView.objects.create(path="/home", ip_address="1.1.1.1", referrer="https://google.com")
        PageView.objects.create(path="/about", ip_address="2.2.2.2", referrer="")
        # One older view (2 days ago) to land inside the 7-day window.
        older = PageView.objects.create(path="/old", ip_address="3.3.3.3")
        PageView.objects.filter(pk=older.pk).update(timestamp=now - timedelta(days=2))

        stats = compute_dashboard_stats()

        self.assertEqual(stats["total_views"], 4)
        self.assertEqual(stats["today_views"], 3)
        self.assertEqual(stats["unique_paths"], 3)
        self.assertEqual(stats["unique_visitors"], 3)
        # /home is the most viewed page.
        self.assertEqual(stats["top_pages"][0]["path"], "/home")
        self.assertEqual(stats["top_pages"][0]["view_count"], 2)
        # google referrer aggregated, blank referrer excluded.
        self.assertEqual(stats["top_referrers"][0]["referrer"], "https://google.com")
        self.assertEqual(stats["top_referrers"][0]["ref_count"], 2)
        # week aggregation reflects all 4 views inside the window.
        self.assertEqual(stats["week_views"], 4)
        self.assertEqual(stats["avg_daily_views"], round(4 / 7, 1))
        self.assertEqual(stats["max_daily_count"], 3)
        # Daily visitor list aligns with the 7 day buckets.
        self.assertEqual(len(stats["last_7_days_visitors"]), 7)
        # Today's hour bucket has the 3 today-views.
        today_total = sum(h["count"] for h in stats["hourly_views"])
        self.assertEqual(today_total, 3)


class IPGeoLookupViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()

    @staticmethod
    def _body(response):
        return json.loads(response.content)

    def test_missing_ip_returns_400(self):
        request = self.factory.get("/ip-geo-lookup/", {"ip": "  "})
        response = ip_geo_lookup_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._body(response)["error"], "No IP provided")

    def test_invalid_ip_returns_400(self):
        request = self.factory.get("/ip-geo-lookup/", {"ip": "not-an-ip"})
        response = ip_geo_lookup_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._body(response)["error"], "Invalid IP address")

    def test_cached_result_returned_without_network(self):
        cache.set(f"{IP_GEO_CACHE_PREFIX}8.8.8.8", {"ip": "8.8.8.8", "city": "Cached City"}, 60)
        request = self.factory.get("/ip-geo-lookup/", {"ip": "8.8.8.8"})

        with patch("requests.get") as mock_get:
            response = ip_geo_lookup_view(request)
            mock_get.assert_not_called()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._body(response)["city"], "Cached City")

    def test_successful_lookup_caches_result(self):
        payload = {
            "status": "success",
            "country": "United States",
            "regionName": "California",
            "city": "Mountain View",
            "zip": "94043",
            "lat": 37.42,
            "lon": -122.08,
            "isp": "Google LLC",
            "org": "Google",
            "as": "AS15169",
        }
        request = self.factory.get("/ip-geo-lookup/", {"ip": "8.8.8.8"})

        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = payload
            response = ip_geo_lookup_view(request)

        self.assertEqual(response.status_code, 200)
        body = self._body(response)
        self.assertEqual(body["country"], "United States")
        self.assertEqual(body["city"], "Mountain View")
        self.assertEqual(body["lat"], 37.42)
        self.assertEqual(body["as"], "AS15169")
        # Result is cached for subsequent lookups.
        self.assertEqual(cache.get(f"{IP_GEO_CACHE_PREFIX}8.8.8.8")["city"], "Mountain View")

    def test_failed_lookup_status_fail_not_cached(self):
        request = self.factory.get("/ip-geo-lookup/", {"ip": "8.8.8.8"})

        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"status": "fail", "message": "reserved range"}
            response = ip_geo_lookup_view(request)

        self.assertEqual(response.status_code, 200)
        body = self._body(response)
        self.assertEqual(body["error"], "reserved range")
        self.assertEqual(body["ip"], "8.8.8.8")
        # Failed lookups are not cached.
        self.assertIsNone(cache.get(f"{IP_GEO_CACHE_PREFIX}8.8.8.8"))

    def test_network_error_returns_502(self):
        request = self.factory.get("/ip-geo-lookup/", {"ip": "8.8.8.8"})

        with patch("requests.get", side_effect=Exception("boom")):
            response = ip_geo_lookup_view(request)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self._body(response)["error"], "Geolocation service unavailable")
