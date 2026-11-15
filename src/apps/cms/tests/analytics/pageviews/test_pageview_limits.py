"""What bounds ``POST /analytics/pageview/`` now that the client IP does not: cache placement, total cap, field sizes.

The per-visitor throttle is keyed on a value the client chooses, so a script can mint a fresh key per request:

- every key is a cache entry. Throttle history therefore lives in the bounded in-process ``throttle`` alias and never
  in the default cache (in production a per-container file cache, where each key is a file and every write lists
  the directory);
- every accepted page view is a row. One constant-key bucket caps all page views of a process at 3,000 a minute,
  far above the campus peak (about 150);
- every row stores request metadata. Each stored field is cut or rejected at its column size.
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.cache import caches
from django.test import override_settings

from apps.cms.views.analytics import (
    PageViewLegacyThrottle,
    PageViewTotalThrottle,
    PageViewVisitorThrottle,
)
from apps.core.utils.throttle_cache import throttle_cache
from config.settings.base.framework.cache import THROTTLE_CACHE

from .test_pageview_visitor import VISITOR_RATE, PageViewVisitorTestCase

TOTAL_RATE = 3000
TOTAL_KEY = "throttle_pageview_total_all"
LEGACY_KEY = "throttle_pageview_legacy_legacy"
WARNED_KEY = "pageview_total_cap_warned"
VIEW_LOGGER = "apps.cms.views.analytics"
THROTTLED_DETAIL = "Request was throttled. Expected available in 60 seconds."


def visitor_key(visitor_id: str) -> str:
    return f"throttle_pageview_visitor_visitor:{visitor_id}"


def stored_keys(alias: str) -> set[str]:
    """Every key a LocMemCache alias holds, as the caller wrote it (without the ``prefix:version:`` part)."""
    return {key.split(":", 2)[2] for key in caches[alias]._cache}


def total_count() -> int:
    """How many page views the total bucket has counted in the current window."""
    return len(throttle_cache.get(TOTAL_KEY, []))


# These floods come from one test client: with the request limiter on, the telemetry scope's per-IP ceiling refuses
# them before the page-view throttles under test run, and its own counters share the throttle cache.
@override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
class ThrottleCachePlacementTests(PageViewVisitorTestCase):
    def test_all_three_throttles_keep_their_history_in_the_throttle_alias(self):
        for throttle in (PageViewVisitorThrottle, PageViewLegacyThrottle, PageViewTotalThrottle):
            with self.subTest(throttle=throttle.__name__):
                self.assertIs(throttle.cache, throttle_cache)
                self.assertIs(throttle().cache, throttle_cache)

    def test_page_views_never_write_to_the_default_cache(self):
        visitor = str(uuid.uuid4())

        statuses = [self.view(visitor) for _ in range(VISITOR_RATE + 1)]
        legacy_status = self.view()

        self.assertEqual(statuses, [201] * VISITOR_RATE + [429])
        self.assertEqual(legacy_status, 201)
        self.assertEqual(stored_keys("default"), set())
        self.assertEqual(stored_keys("throttle"), {visitor_key(visitor), LEGACY_KEY, TOTAL_KEY})
        self.assertEqual(len(throttle_cache.get(visitor_key(visitor))), VISITOR_RATE)
        self.assertEqual(len(throttle_cache.get(LEGACY_KEY)), 1)

    def test_page_views_are_throttled_while_the_default_cache_refuses_every_call(self):
        refuse = Mock(side_effect=AssertionError("a page view touched the default cache"))
        visitor = str(uuid.uuid4())

        with patch.multiple(caches["default"], get=refuse, set=refuse, add=refuse, incr=refuse, touch=refuse):
            statuses = [self.view(visitor) for _ in range(VISITOR_RATE + 1)]
            legacy_status = self.view()

        refuse.assert_not_called()
        self.assertEqual(statuses, [201] * VISITOR_RATE + [429])
        self.assertEqual(legacy_status, 201)

    def test_minted_ids_leave_no_file_in_a_production_style_file_cache(self):
        """The production default cache without Redis: one file per key, the directory listed on every write."""
        with tempfile.TemporaryDirectory() as directory:
            production_like = {
                "default": {
                    "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                    "LOCATION": directory,
                    "KEY_PREFIX": "i2g",
                    "OPTIONS": {"MAX_ENTRIES": 2_000},
                },
                "throttle": {**THROTTLE_CACHE, "LOCATION": "pageview-file-cache-probe"},
            }
            with override_settings(CACHES=production_like):
                self.addCleanup(caches["throttle"].clear)

                statuses = [self.view(str(uuid.uuid4())) for _ in range(300)]
                statuses.append(self.view())

                self.assertEqual(statuses, [201] * 301)
                self.assertEqual(list(Path(directory).iterdir()), [])
                # 300 visitor buckets, the legacy bucket and the total bucket.
                self.assertEqual(len(caches["throttle"]._cache), 302)
                caches["throttle"].clear()

    def test_a_flood_of_minted_ids_cannot_grow_the_throttle_cache_past_its_cap(self):
        small = {**THROTTLE_CACHE, "LOCATION": "pageview-bound-probe", "OPTIONS": {"MAX_ENTRIES": 50}}
        with override_settings(CACHES={**settings.CACHES, "throttle": small}):
            self.addCleanup(caches["throttle"].clear)
            sizes = []
            for _ in range(400):
                self.assertEqual(self.view(str(uuid.uuid4())), 201)
                sizes.append(len(caches["throttle"]._cache))

            # 400 minted ids, never more than 50 entries: each cull drops the least recently used third.
            self.assertLessEqual(max(sizes), 50)
            self.assertGreater(max(sizes), 40)
            self.assertLess(min(sizes[100:]), max(sizes))
            # The bucket every request reads is never the least recently used entry, so the culls spare it.
            self.assertEqual(total_count(), 400)
            self.assertEqual(stored_keys("default"), set())
            caches["throttle"].clear()
