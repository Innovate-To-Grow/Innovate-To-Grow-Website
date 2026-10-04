"""The ``throttle`` cache alias: bounded, in-process history for throttles whose key the caller chooses.

A DRF throttle keeps one cache entry per key. When the key comes from an anonymous request body (the page-view
``visitor_id``, the assistant visitor token), anyone can mint as many entries as they send requests. In the default
production cache, a per-container ``FileBasedCache``, every entry is a file: Django lists the whole directory on
each write, so every cache write in the container slows down with the file count, and at ``MAX_ENTRIES`` a random
third of all entries is deleted. Such throttles therefore set ``cache = throttle_cache``: a ``LocMemCache`` with a
hard entry ceiling and least-recently-used culling (``THROTTLE_CACHE`` in
``config/settings/components/framework/cache.py``), where a minted key costs a few hundred bytes and evicts only
other stale keys.

The alias is per PROCESS: each Uvicorn worker has its own history and a restart forgets it, so the effective rate
is the nominal rate times ``WEB_CONCURRENCY`` times the task count. Use it only for fairness limiters that fail
open. Never keep a counter that bounds security or money here (login lockout, send quotas, token budgets): those
live in PostgreSQL.
"""

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.utils.connection import ConnectionProxy

THROTTLE_CACHE_ALIAS = "throttle"

# Resolved on every access, like ``django.core.cache.cache``, so ``override_settings(CACHES=...)`` is honoured. A
# settings module without the alias fails loudly (``InvalidCacheBackendError``) instead of spilling into ``default``.
throttle_cache = ConnectionProxy(caches, THROTTLE_CACHE_ALIAS)


class DevelopmentLocMemCache(LocMemCache):
    """The development / CI ``default`` cache: ``clear()`` empties the ``throttle`` alias as well.

    Tests reset cache-backed state with ``cache.clear()`` in ``setUp``. Throttle history used to be part of that
    cache; with this backend it still goes away, so a test never inherits another test's request counts. Production
    uses Redis or the file cache for ``default`` and never this class.
    """

    def clear(self):
        super().clear()
        if THROTTLE_CACHE_ALIAS in settings.CACHES:
            caches[THROTTLE_CACHE_ALIAS].clear()
