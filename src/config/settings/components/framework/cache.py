"""
Cache aliases shared by every environment.

``default`` here is the development / CI cache; ``local.py`` renames its location and the production overlay
replaces it (Redis, or the per-container file cache). ``throttle`` is the same everywhere: every settings module
that defines ``CACHES`` must include ``"throttle": THROTTLE_CACHE``.
"""

# A bounded, in-process cache for the DRF throttles whose key an anonymous caller chooses (the page-view
# ``visitor_id``, the assistant visitor token, a forgeable X-Forwarded-For string) and for the total page-view cap. Every minted key is one entry, so
# that history must never go to the production file cache: Django lists the whole cache directory on every write,
# so each write gets slower with every key, and at the cap a random third of ALL entries is deleted, unrelated
# cache state included. Here 50,000 entries is a hard ceiling (about 16 MB per process when full of single-request keys, up to about
# 70 MB if every key held a full history), a write costs
# the same whatever the fill, and LocMemCache culls the least-recently-used third, so a flood of minted keys evicts
# its own stale keys rather than the buckets in use.
#
# Per PROCESS, not per container: each Uvicorn worker (WEB_CONCURRENCY, default 2) has its own copy and a restart
# forgets it, so a rate kept here is effectively multiplied by the worker count and the task count. That is fine
# for fairness limiters and speed bumps that fail open, and for nothing else: no counter that is the actual bound
# on security or money may use this alias (those are in PostgreSQL).
THROTTLE_CACHE = {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "i2g-throttle",
    "TIMEOUT": 60,
    "OPTIONS": {"MAX_ENTRIES": 50_000, "CULL_FREQUENCY": 3},
}

CACHES = {
    "default": {
        # LocMemCache whose clear() also empties the throttle alias, so that the ``cache.clear()`` every test
        # runs in setUp keeps resetting throttle history. Development and CI only.
        "BACKEND": "apps.core.utils.throttle_cache.DevelopmentLocMemCache",
        "LOCATION": "innovate-to-grow",
    },
    "throttle": THROTTLE_CACHE,
}
