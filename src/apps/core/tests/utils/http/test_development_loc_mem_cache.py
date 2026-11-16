from django.core.cache import cache, caches
from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, override_settings

from apps.core.tests.utils.http.test_throttle_cache import DEVELOPMENT
from apps.core.utils.throttle_cache import DevelopmentLocMemCache, throttle_cache


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
