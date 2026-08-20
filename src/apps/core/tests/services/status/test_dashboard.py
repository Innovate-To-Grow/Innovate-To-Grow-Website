from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.core.services.status.client import StatusFetchError
from apps.core.services.status.dashboard import (
    FRESH_CACHE_TTL,
    LAST_GOOD_CACHE_TTL,
    NEGATIVE_CACHE_TTL,
    get_infrastructure_dashboard,
    get_public_status_url,
)

VALID_URL = "https://abc123def4.execute-api.us-west-2.amazonaws.com/prod/internal/status"


def payload(*, partial=False):
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-08-20T10:00:00Z",
        "partial": partial,
        "errors": [{"source": "ecs", "code": "timeout", "message": "Unavailable"}] if partial else [],
        "stack": {"name": "i2g-status", "resources": []},
        "services": [],
        "probes": [],
        "alarms": [],
    }


class FakeClient:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def fetch(self):
        result = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


@override_settings(
    STATUS_INTERNAL_API_URL=VALID_URL,
    STATUS_API_REGION="us-west-2",
    STATUS_PUBLIC_URL="https://status.i2g.ucmerced.edu/",
)
class InfrastructureDashboardCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.now = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)

    def tearDown(self):
        cache.clear()

    def test_cache_policy_constants_are_bounded(self):
        self.assertEqual(FRESH_CACHE_TTL, 30)
        self.assertEqual(LAST_GOOD_CACHE_TTL, 900)
        self.assertEqual(NEGATIVE_CACHE_TTL, 10)

    def test_second_request_uses_30_second_fresh_cache(self):
        client = FakeClient(payload())

        first = get_infrastructure_dashboard(client=client, now=self.now)
        second = get_infrastructure_dashboard(client=client, now=self.now + timedelta(seconds=5))

        self.assertEqual(client.calls, 1)
        self.assertEqual(first["cacheState"], "refreshed")
        self.assertEqual(second["cacheState"], "fresh")
        self.assertTrue(second["available"])
        self.assertFalse(second["stale"])

    def test_force_bypasses_fresh_cache_and_rewarms_it(self):
        first_payload = payload()
        second_payload = payload(partial=True)
        client = FakeClient(first_payload, second_payload)

        get_infrastructure_dashboard(client=client, now=self.now)
        forced = get_infrastructure_dashboard(client=client, force=True, now=self.now + timedelta(seconds=1))
        cached = get_infrastructure_dashboard(client=client, now=self.now + timedelta(seconds=2))

        self.assertEqual(client.calls, 2)
        self.assertTrue(forced["status"]["partial"])
        self.assertTrue(cached["status"]["partial"])

    def test_failure_returns_last_good_snapshot_as_stale(self):
        client = FakeClient(payload(), StatusFetchError("timeout"))
        get_infrastructure_dashboard(client=client, now=self.now)

        result = get_infrastructure_dashboard(client=client, force=True, now=self.now + timedelta(minutes=2))

        self.assertTrue(result["available"])
        self.assertTrue(result["stale"])
        self.assertEqual(result["reason"], "timeout")
        self.assertEqual(result["staleAgeSeconds"], 120)
        self.assertEqual(result["status"]["schemaVersion"], 1)

        cached_failure = get_infrastructure_dashboard(client=client, now=self.now + timedelta(minutes=2, seconds=1))
        self.assertTrue(cached_failure["stale"])
        self.assertEqual(cached_failure["cacheState"], "negative")
        self.assertEqual(client.calls, 2)

    def test_failure_without_last_good_is_unavailable_and_negative_cached(self):
        client = FakeClient(StatusFetchError("permission"), payload())

        first = get_infrastructure_dashboard(client=client, now=self.now)
        second = get_infrastructure_dashboard(client=client, now=self.now + timedelta(seconds=1))

        self.assertEqual(client.calls, 1)
        self.assertFalse(first["available"])
        self.assertEqual(first["reason"], "permission")
        self.assertEqual(second["cacheState"], "negative")
        self.assertNotIn("arn:aws", second["message"])

    def test_force_ignores_negative_cache(self):
        client = FakeClient(StatusFetchError("upstream"), payload())
        get_infrastructure_dashboard(client=client, now=self.now)

        result = get_infrastructure_dashboard(client=client, force=True, now=self.now + timedelta(seconds=1))

        self.assertEqual(client.calls, 2)
        self.assertTrue(result["available"])
        self.assertEqual(result["cacheState"], "refreshed")

    def test_partial_payload_remains_available(self):
        result = get_infrastructure_dashboard(client=FakeClient(payload(partial=True)), now=self.now)
        self.assertTrue(result["available"])
        self.assertFalse(result["stale"])
        self.assertTrue(result["status"]["partial"])

    def test_malformed_cached_timestamp_does_not_break_dashboard(self):
        malformed_record = {"status": payload(), "fetchedAt": "2026-08-20T10:00:00"}
        with patch("apps.core.services.status.dashboard.cache.get", return_value=malformed_record):
            result = get_infrastructure_dashboard(client=FakeClient(payload()), now=self.now)

        self.assertTrue(result["available"])
        self.assertIsNone(result["staleAgeSeconds"])

    def test_public_status_url_allows_only_https_without_credentials_or_fragment(self):
        self.assertEqual(get_public_status_url(), "https://status.i2g.ucmerced.edu/")
        invalid = (
            "http://status.example.com",
            "javascript:alert(1)",
            "https://user:pass@status.example.com",
            "https://status.example.com/#fragment",
        )
        for value in invalid:
            with self.subTest(value=value), override_settings(STATUS_PUBLIC_URL=value):
                self.assertEqual(get_public_status_url(), "")
