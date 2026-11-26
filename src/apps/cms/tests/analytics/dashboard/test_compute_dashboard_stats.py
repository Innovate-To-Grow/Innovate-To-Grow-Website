import json
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.cms.admin.analytics.page_view.geo import IP_GEO_CACHE_PREFIX, ip_geo_lookup_view
from apps.cms.admin.analytics.page_view.stats import (
    compute_dashboard_stats,
)
from apps.cms.models import PageView
from apps.event.tests.helpers import make_superuser


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
        # The view is reached only through ``admin_view`` (Admins only); sign the raw request in as one.
        self.user = make_superuser(email="geo-lookup-admin@example.com")

    def tearDown(self):
        cache.clear()

    def _get(self, params):
        request = self.factory.get("/ip-geo-lookup/", params)
        request.user = self.user
        return request

    @staticmethod
    def _body(response):
        return json.loads(response.content)

    def test_missing_ip_returns_400(self):
        request = self._get({"ip": "  "})
        response = ip_geo_lookup_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._body(response)["error"], "No IP provided")

    def test_invalid_ip_returns_400(self):
        request = self._get({"ip": "not-an-ip"})
        response = ip_geo_lookup_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._body(response)["error"], "Invalid IP address")

    def test_cached_result_returned_without_network(self):
        cache.set(f"{IP_GEO_CACHE_PREFIX}8.8.8.8", {"ip": "8.8.8.8", "city": "Cached City"}, 60)
        request = self._get({"ip": "8.8.8.8"})

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
        request = self._get({"ip": "8.8.8.8"})

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
        request = self._get({"ip": "8.8.8.8"})

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
        request = self._get({"ip": "8.8.8.8"})

        with patch("requests.get", side_effect=Exception("boom")):
            response = ip_geo_lookup_view(request)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self._body(response)["error"], "Geolocation service unavailable")
