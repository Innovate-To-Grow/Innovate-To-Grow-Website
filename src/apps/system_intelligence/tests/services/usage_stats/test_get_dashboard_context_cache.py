from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.system_intelligence.services.usage_stats import dashboard as dashboard_module
from apps.system_intelligence.services.usage_stats import (
    get_dashboard_context,
)


class GetDashboardContextCacheTest(TestCase):
    def setUp(self):
        cache.delete(dashboard_module.CLOUDWATCH_CACHE_KEY)
        cache.delete(dashboard_module.LOCAL_CACHE_KEY)

    def tearDown(self):
        cache.delete(dashboard_module.CLOUDWATCH_CACHE_KEY)
        cache.delete(dashboard_module.LOCAL_CACHE_KEY)

    def test_second_call_hits_cache(self):
        cw = {"available": True, "marker": "first"}
        with patch.object(dashboard_module, "fetch_bedrock_metrics", return_value=cw) as fetch:
            first = get_dashboard_context()
            second = get_dashboard_context()
        self.assertEqual(first["cloudwatch"], cw)
        self.assertEqual(second["cloudwatch"], cw)
        self.assertNotIn("local", first)
        self.assertNotIn("local", second)
        # The underlying CloudWatch computation ran exactly once -- the second call was cached.
        fetch.assert_called_once()

    def test_force_bypasses_cache_read_but_writes(self):
        with patch.object(dashboard_module, "fetch_bedrock_metrics", return_value={"v": 1}):
            get_dashboard_context()  # warm the cache

        with patch.object(dashboard_module, "fetch_bedrock_metrics", return_value={"v": 2}) as fetch:
            forced = get_dashboard_context(force=True)
        # force=True recomputes even though the cache was warm.
        fetch.assert_called_once()
        self.assertEqual(forced["cloudwatch"], {"v": 2})
        self.assertNotIn("local", forced)
        # And the fresh value is written back for the next non-forced read.
        self.assertEqual(cache.get(dashboard_module.CLOUDWATCH_CACHE_KEY), {"v": 2})
