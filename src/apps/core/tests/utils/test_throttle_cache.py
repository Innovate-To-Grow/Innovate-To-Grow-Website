"""The ``throttle`` cache alias: a bounded in-process cache, separate from ``default``, in every settings module.

Throttles whose key an anonymous caller mints keep their history here. In the production file cache every minted
key was one more file, which made each cache write of the container slower and, at the cap, culled unrelated state.
"""

import importlib

from django.conf import settings
from django.core.cache import InvalidCacheBackendError, cache, caches
from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, override_settings

from apps.core.utils.throttle_cache import THROTTLE_CACHE_ALIAS, DevelopmentLocMemCache, throttle_cache
from config.settings.components.framework.cache import CACHES as BASE_CACHES
from config.settings.components.framework.cache import THROTTLE_CACHE

LOCMEM = "django.core.cache.backends.locmem.LocMemCache"
DEVELOPMENT = "apps.core.utils.throttle_cache.DevelopmentLocMemCache"


def small_caches(max_entries, cull_frequency=3, location="throttle-cache-tests"):
    return {
        "default": {"BACKEND": DEVELOPMENT, "LOCATION": f"{location}-default"},
        "throttle": {
            "BACKEND": LOCMEM,
            "LOCATION": location,
            "OPTIONS": {"MAX_ENTRIES": max_entries, "CULL_FREQUENCY": cull_frequency},
        },
    }


class ThrottleCacheSettingsTests(SimpleTestCase):
    def test_the_alias_is_a_bounded_in_process_cache(self):
        self.assertEqual(THROTTLE_CACHE_ALIAS, "throttle")
        self.assertEqual(THROTTLE_CACHE["BACKEND"], LOCMEM)
        self.assertEqual(THROTTLE_CACHE["OPTIONS"]["MAX_ENTRIES"], 50_000)
        # 0 would empty the whole cache at the cap (every bucket in use included); 3 drops the stalest third.
        self.assertEqual(THROTTLE_CACHE["OPTIONS"]["CULL_FREQUENCY"], 3)
        self.assertTrue(THROTTLE_CACHE["LOCATION"])

    def test_the_running_settings_define_it_next_to_a_separate_default(self):
        self.assertEqual(settings.CACHES["throttle"], THROTTLE_CACHE)
        self.assertEqual(settings.CACHES["default"]["BACKEND"], DEVELOPMENT)
        # Two LocMemCache aliases with one LOCATION would be one store.
        self.assertNotEqual(settings.CACHES["default"]["LOCATION"], THROTTLE_CACHE["LOCATION"])
        self.assertIsNot(caches["throttle"], caches["default"])
        self.assertIsNot(caches["throttle"]._cache, caches["default"]._cache)
        self.assertEqual(caches["throttle"]._max_entries, 50_000)
        self.assertEqual(caches["throttle"]._cull_frequency, 3)

    def test_base_local_and_ci_settings_all_define_it(self):
        self.assertEqual(BASE_CACHES["throttle"], THROTTLE_CACHE)
        for module_name in ("config.settings.base", "config.settings.local", "config.settings.test"):
            with self.subTest(settings=module_name):
                module = importlib.import_module(module_name)
                self.assertEqual(module.CACHES["throttle"], THROTTLE_CACHE)
                self.assertEqual(module.CACHES["default"]["BACKEND"], DEVELOPMENT)
                self.assertNotEqual(module.CACHES["default"]["LOCATION"], THROTTLE_CACHE["LOCATION"])


class ThrottleCacheProxyTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_the_proxy_is_the_throttle_alias_and_not_the_default_cache(self):
        throttle_cache.set("throttle-cache-test", [1.0], 60)

        self.assertEqual(caches["throttle"].get("throttle-cache-test"), [1.0])
        self.assertIsNone(cache.get("throttle-cache-test"))
        self.assertEqual(list(caches["default"]._cache), [])

    def test_the_default_cache_is_not_visible_through_the_proxy(self):
        cache.set("default-cache-test", "value", 60)

        self.assertIsNone(throttle_cache.get("default-cache-test"))
        self.assertEqual(list(caches["throttle"]._cache), [])

    def test_the_proxy_follows_overridden_settings(self):
        with override_settings(CACHES=small_caches(7, location="throttle-cache-proxy")):
            self.assertEqual(throttle_cache._max_entries, 7)
            throttle_cache.set("inside", 1, 60)
            self.assertEqual(caches["throttle"].get("inside"), 1)
            throttle_cache.clear()

        self.assertEqual(throttle_cache._max_entries, 50_000)
        self.assertIsNone(throttle_cache.get("inside"))

    def test_a_settings_module_without_the_alias_fails_loudly_instead_of_using_default(self):
        with override_settings(CACHES={"default": {"BACKEND": LOCMEM, "LOCATION": "throttle-cache-missing"}}):
            with self.assertRaises(InvalidCacheBackendError):
                throttle_cache.set("minted", [1.0], 60)

            self.assertEqual(list(caches["default"]._cache), [])


class ForgeableKeyThrottleTests(SimpleTestCase):
    """Per-IP throttles key on the caller-supplied X-Forwarded-For string, so they must not use ``default``."""

    def test_the_sms_fallback_and_ses_webhook_throttles_use_the_throttle_alias(self):
        from apps.authn.security.throttles import PhoneAuthCodeRequestThrottle
        from apps.mail.views.ses_webhook import SesEventThrottle

        for throttle_class in (PhoneAuthCodeRequestThrottle, SesEventThrottle):
            with self.subTest(throttle=throttle_class.__name__):
                self.assertIs(throttle_class.cache, throttle_cache)

    def test_a_forged_forwarded_for_flood_on_the_ses_webhook_leaves_the_default_cache_empty(self):
        from rest_framework.test import APIClient

        cache.clear()
        self.addCleanup(cache.clear)
        client = APIClient()
        statuses = [
            client.post(
                "/mail/ses/events/",
                "[]",  # not an SNS envelope: answered 400 once the throttle has run, before any signature check
                content_type="application/json",
                HTTP_X_FORWARDED_FOR=f"203.0.113.{index}, 10.0.0.1",
            ).status_code
            for index in range(40)
        ]

        self.assertEqual(set(statuses), {400})
        self.assertEqual(list(caches["default"]._cache), [])
        self.assertGreater(len(caches["throttle"]._cache), 0)


class ThrottleCacheBoundTests(SimpleTestCase):
    def test_minted_keys_never_exceed_max_entries(self):
        with override_settings(CACHES=small_caches(30, location="throttle-cache-bound")):
            self.addCleanup(caches["throttle"].clear)
            sizes = []
            for index in range(1000):
                throttle_cache.set(f"throttle_pageview_visitor_visitor:minted-{index}", [float(index)], 60)
                sizes.append(len(caches["throttle"]._cache))

            self.assertEqual(max(sizes), 30)
            self.assertEqual(len(caches["throttle"]._expire_info), len(caches["throttle"]._cache))
            # The newest key is there; the oldest ones were culled.
            self.assertEqual(throttle_cache.get("throttle_pageview_visitor_visitor:minted-999"), [999.0])
            self.assertIsNone(throttle_cache.get("throttle_pageview_visitor_visitor:minted-0"))

    def test_a_bucket_in_use_survives_a_flood_of_minted_keys(self):
        """The cull drops the least recently used entries, so a flood evicts its own stale keys."""
        with override_settings(CACHES=small_caches(30, location="throttle-cache-lru")):
            self.addCleanup(caches["throttle"].clear)
            throttle_cache.set("throttle_pageview_total_all", [0.0], 60)
            for index in range(1000):
                throttle_cache.set(f"throttle_pageview_visitor_visitor:minted-{index}", [float(index)], 60)
                history = throttle_cache.get("throttle_pageview_total_all")  # read on every request
                self.assertIsNotNone(history, index)
                throttle_cache.set("throttle_pageview_total_all", [*history, float(index)], 60)

            self.assertEqual(len(throttle_cache.get("throttle_pageview_total_all")), 1001)
            self.assertLessEqual(len(caches["throttle"]._cache), 30)

    def test_the_production_sized_alias_holds_exactly_its_cap(self):
        location = "throttle-cache-full-size"
        with override_settings(CACHES={**settings.CACHES, "throttle": {**THROTTLE_CACHE, "LOCATION": location}}):
            self.addCleanup(caches["throttle"].clear)
            limit = THROTTLE_CACHE["OPTIONS"]["MAX_ENTRIES"]
            for index in range(limit):
                throttle_cache.set(f"k{index}", 1, 60)
            self.assertEqual(len(caches["throttle"]._cache), limit)

            throttle_cache.set("one-more", 1, 60)

            # A third of the entries (the stalest) made room; the cache never held more than the cap.
            self.assertEqual(len(caches["throttle"]._cache), limit - limit // 3 + 1)
            self.assertIsNone(throttle_cache.get("k0"))
            self.assertEqual(throttle_cache.get(f"k{limit - 1}"), 1)


class DevelopmentLocMemCacheTests(SimpleTestCase):
    def test_it_is_a_locmem_cache(self):
        self.assertIsInstance(caches["default"], DevelopmentLocMemCache)
        self.assertTrue(issubclass(DevelopmentLocMemCache, LocMemCache))

    def test_clearing_the_default_cache_also_clears_throttle_history(self):
        """Tests call ``cache.clear()`` in setUp; that must keep resetting every throttle."""
        cache.set("read-cache", "value", 60)
        throttle_cache.set("throttle_public_assistant_legacy:legacy", [1.0, 2.0], 60)

        cache.clear()

        self.assertIsNone(cache.get("read-cache"))
        self.assertIsNone(throttle_cache.get("throttle_public_assistant_legacy:legacy"))
        self.assertEqual(len(caches["throttle"]._cache), 0)

    def test_clearing_the_throttle_cache_leaves_the_default_cache_alone(self):
        cache.set("read-cache", "value", 60)
        self.addCleanup(cache.clear)

        throttle_cache.clear()

        self.assertEqual(cache.get("read-cache"), "value")

    def test_clear_works_when_no_throttle_alias_is_configured(self):
        with override_settings(CACHES={"default": {"BACKEND": DEVELOPMENT, "LOCATION": "throttle-cache-no-alias"}}):
            cache.set("read-cache", "value", 60)

            cache.clear()

            self.assertIsNone(cache.get("read-cache"))
