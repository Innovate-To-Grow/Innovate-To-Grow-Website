"""Redis and per-container file-cache settings for production."""

import os
import tempfile

from ..base.framework.cache import THROTTLE_CACHE

# Caching (Redis preferred; falls back to file-based cache). Both branches carry the same ``throttle`` alias: the
# bounded in-process cache for throttles keyed on a value an anonymous caller mints (see base/framework/cache.py).
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
CACHES = (
    {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "i2g",
            "TIMEOUT": 300,  # 5-minute default TTL
        },
        "throttle": THROTTLE_CACHE,
    }
    if REDIS_URL
    else {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": os.environ.get(
                "DJANGO_CACHE_DIR",
                os.path.join(tempfile.gettempdir(), "innovate-to-grow-cache"),
            ),
            "KEY_PREFIX": "i2g",
            "TIMEOUT": 300,
            # Per container and non-atomic. Nothing that bounds security or money lives here: the password-login
            # lockout (member and admin-panel sign-in), send-verification quotas and the assistant / AI-search
            # token budgets are in PostgreSQL. What is here: read caches, the per-member DRF throttles, the admin
            # confirm-on-save payloads, CMS preview payloads and the per-invitation attempt counter.
            # Every write lists this directory, so its cost grows with the file count (about 0.8 ms per 1,000
            # files, measured). MAX_ENTRIES is therefore a small bound: enough for the legitimate entries, and a
            # flood of junk keys can never slow cache writes by more than a few milliseconds. Above it Django
            # culls a random third. A throttle whose key an anonymous caller can mint must use the ``throttle``
            # alias below, never this cache (see docs/deployment/environments.md).
            "OPTIONS": {"MAX_ENTRIES": 2_000},
        },
        "throttle": THROTTLE_CACHE,
    }
)
