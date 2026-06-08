"""Tests for the assistant usage dashboard admin views (CloudWatch mocked)."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.models import AssistantConversationLog
from apps.system_intelligence.services.usage_stats import dashboard as dashboard_module

# Patch where fetch_bedrock_metrics is *used* so no boto3 call ever happens.
FETCH_PATH = "apps.system_intelligence.services.usage_stats.dashboard.fetch_bedrock_metrics"

_EMPTY_CW = {
    "available": False,
    "reason": "unconfigured",
    "by_model": [],
    "daily": [],
    "today": {"input_tokens": 0, "output_tokens": 0, "invocations": 0},
    "totals": {"input_tokens": 0, "output_tokens": 0, "invocations": 0},
}


class UsageDashboardViewTest(TestCase):
    def setUp(self):
        self.superuser = make_superuser(email="usageadmin@example.com")
        self.client.force_login(self.superuser)
        cache.delete(dashboard_module.CLOUDWATCH_CACHE_KEY)
        cache.delete(dashboard_module.LOCAL_CACHE_KEY)
        AssistantConversationLog.objects.create(
            source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            message_count=1,
            total_tokens=10,
            last_activity_at=timezone.now(),
        )

    def tearDown(self):
        cache.delete(dashboard_module.CLOUDWATCH_CACHE_KEY)
        cache.delete(dashboard_module.LOCAL_CACHE_KEY)

    def test_page_renders_for_staff(self):
        with patch(FETCH_PATH, return_value=_EMPTY_CW) as fetch:
            response = self.client.get(reverse("admin:system_intelligence_usage_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/system_intelligence/usage_dashboard.html")
        self.assertContains(response, "Assistant Usage")
        # The banner reason is embedded in the injected JSON.
        self.assertContains(response, "unconfigured")
        self.assertContains(response, "si-usage-refresh")
        self.assertNotContains(response, "si-usage-fullscreen")
        fetch.assert_called_once()

    def test_page_uses_theme_aware_dashboard_assets(self):
        with patch(FETCH_PATH, return_value=_EMPTY_CW):
            response = self.client.get(reverse("admin:system_intelligence_usage_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "system_intelligence/css/usage-dashboard.css?v=20260608-model-wide")
        self.assertContains(response, "CloudWatch Bedrock metrics for 30-day token")
        self.assertContains(response, "si-usage-title")
        self.assertContains(response, "si-usage-hero-row")
        self.assertContains(response, "si-usage-hero-copy")
        self.assertContains(response, "si-usage-scroll-panel")
        self.assertContains(response, "si-usage-scroll-body")
        self.assertContains(response, "lg:col-span-2")
        self.assertContains(response, 'data-stat-label="today_input"')
        self.assertContains(response, 'data-stat-detail="today_input"')
        self.assertContains(response, "Input Tokens (30d)")
        self.assertContains(response, "Output Tokens (30d)")
        self.assertContains(response, "Invocations (30d)")
        self.assertContains(response, "CloudWatch Bedrock total")
        self.assertContains(response, "renderFallbackBars")
        self.assertContains(response, "si-usage-fallback-chart")
        self.assertContains(response, "preferSvgCharts")
        self.assertContains(response, "function palette()")
        self.assertContains(response, "new MutationObserver")
        self.assertNotContains(response, "Tokens by Source (30d)")
        self.assertNotContains(response, "Recent Conversations")
        self.assertNotContains(response, "Top Prompts (30d)")
        self.assertNotContains(response, "Cache Read (24h)")
        self.assertNotContains(response, "Cache Write (24h)")
        self.assertNotContains(response, "Cache Hit Rate")
        self.assertNotContains(response, "Conversations Today")
        self.assertNotContains(response, "Messages (7d)")
        self.assertNotContains(response, "si-usage-local")
        self.assertNotContains(response, "Application audit logs")
        self.assertNotContains(response, "From local audit logs")
        self.assertNotContains(response, "Logged assistant turns")
        self.assertNotContains(response, "preferLocal")
        self.assertNotContains(response, "hasPositiveMetric")
        self.assertNotContains(response, "cdn.jsdelivr.net/npm/chart.js")
        self.assertNotContains(response, "cdn.jsdelivr.net/npm/chartjs-plugin-datalabels")
        self.assertNotContains(response, "rgba(255,255,255,0.6)")
        self.assertNotContains(response, "rgba(0,0,0,0.5)")

    def test_page_redirects_anonymous_to_login(self):
        self.client.logout()
        url = reverse("admin:system_intelligence_usage_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_data_endpoint_returns_json_with_expected_keys(self):
        with patch(FETCH_PATH, return_value=_EMPTY_CW):
            response = self.client.get(reverse("admin:system_intelligence_usage_data"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        payload = response.json()
        self.assertIn("cloudwatch", payload)
        self.assertNotIn("local", payload)
        self.assertFalse(payload["cloudwatch"]["available"])

    def test_data_endpoint_force_bypasses_cache(self):
        # Warm the cache with one value, then force a recompute with another.
        with patch(FETCH_PATH, return_value=dict(_EMPTY_CW, reason="first")):
            self.client.get(reverse("admin:system_intelligence_usage_data"))
        with patch(FETCH_PATH, return_value=dict(_EMPTY_CW, reason="second")) as fetch:
            response = self.client.get(reverse("admin:system_intelligence_usage_data"), {"force": "1"})
        fetch.assert_called_once()
        self.assertEqual(response.json()["cloudwatch"]["reason"], "second")

    def test_data_endpoint_redirects_anonymous(self):
        self.client.logout()
        response = self.client.get(reverse("admin:system_intelligence_usage_data"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
