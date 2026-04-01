import importlib
from unittest.mock import patch

from django.test import SimpleTestCase


def reload_prod_settings():
    import core.settings.components.production as production_settings
    import core.settings.prod as prod_settings

    importlib.reload(production_settings)
    return importlib.reload(prod_settings)


class ProductionCacheSettingsTests(SimpleTestCase):
    def test_prod_uses_redis_cache_when_configured(self):
        with patch.dict(
            "os.environ",
            {"REDIS_URL": "redis://cache.example.com:6379/0"},
            clear=False,
        ):
            prod_settings = reload_prod_settings()

        self.assertEqual(prod_settings.CACHES["default"]["BACKEND"], "django_redis.cache.RedisCache")
        self.assertEqual(prod_settings.CACHES["default"]["LOCATION"], "redis://cache.example.com:6379/0")

    def test_prod_uses_file_based_cache_without_redis(self):
        cache_dir = "/tmp/i2g-test-cache"
        with patch.dict(
            "os.environ",
            {"REDIS_URL": "", "DJANGO_CACHE_DIR": cache_dir},
            clear=False,
        ):
            prod_settings = reload_prod_settings()

        self.assertEqual(
            prod_settings.CACHES["default"]["BACKEND"], "django.core.cache.backends.filebased.FileBasedCache"
        )
        self.assertEqual(prod_settings.CACHES["default"]["LOCATION"], cache_dir)
