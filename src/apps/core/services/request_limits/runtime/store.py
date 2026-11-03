"""Request counters.

**Shared** mode (the default cache is Redis, ``store.shared_backends``): one atomic counter per bucket and window
for every process, so a limit is exact site-wide. **Local** mode (no shared cache, as in production today): each
process counts in its own bounded ``throttle`` cache and enforces ``limit / live processes`` (``heartbeat``), so
the site-wide total is approximately the limit.

Windows are **fixed**: the counter for ``floor(now / period)`` is created with ``add`` (atomic) and counted with
``incr`` (atomic in Redis and inside one process), so one request costs two cache calls and no lock. A caller can
send up to twice the limit across a window boundary; that is accepted for a flood guard (a sliding log would cost
one entry per request), and the finer per-view throttles keep their sliding windows.

Every call fails open: a cache error lets the request through and is logged, it never fails the request.
Keys are hashed, so no client IP or token ever appears in a cache key.
"""

import hashlib
import logging
import math

from django.conf import settings
from django.core.cache import caches

from apps.core.utils.throttle_cache import THROTTLE_CACHE_ALIAS

from .context import section

logger = logging.getLogger(__name__)

SHARED = "shared"
LOCAL = "local"


def mode() -> str:
    """``shared`` or ``local``: which counter store is active."""
    store = section("store")
    if store["mode"] != "auto":
        return store["mode"]
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    return SHARED if backend in store["shared_backends"] else LOCAL


def _cache():
    return caches["default"] if mode() == SHARED else caches[THROTTLE_CACHE_ALIAS]


def key(*parts: str) -> str:
    digest = hashlib.blake2b("|".join(parts).encode(), digest_size=16).hexdigest()
    return f"rl:{digest}"


def window_reset(period: int, now: float) -> int:
    """Whole seconds until the fixed window that holds ``now`` ends (at least 1)."""
    return max(1, math.ceil((math.floor(now / period) + 1) * period - now))


def window_key(bucket: str, period: int, now: float) -> str:
    """The counter of ``bucket``'s window that holds ``now``."""
    return key("hit", bucket, str(period), str(math.floor(now / period)))


def hit(bucket: str, period: int, now: float, *, keep: int | None = None) -> int:
    """Count one request in ``bucket``'s current window; return the window's count including it (0 on a cache
    error, which therefore never refuses). The counter lives ``keep`` seconds (default: the window and one more)."""
    name = window_key(bucket, period, now)
    timeout = period + 1 if keep is None else keep
    cache = _cache()
    try:
        cache.add(name, 0, timeout=timeout)
        return cache.incr(name)
    except ValueError:
        # The entry expired or was culled between add and incr: this request opens it again.
        cache.set(name, 1, timeout=timeout)
        return 1
    except Exception:
        logger.warning("request_limits.store_unavailable", exc_info=True)
        return 0


def get(name: str):
    try:
        return _cache().get(name)
    except Exception:
        logger.warning("request_limits.store_unavailable", exc_info=True)
        return None


def get_many(names: list[str]) -> dict:
    try:
        return _cache().get_many(names)
    except Exception:
        logger.warning("request_limits.store_unavailable", exc_info=True)
        return {}


def put(name: str, value, timeout: float) -> None:
    try:
        _cache().set(name, value, timeout=max(1, math.ceil(timeout)))
    except Exception:
        logger.warning("request_limits.store_unavailable", exc_info=True)


def delete(name: str) -> None:
    try:
        _cache().delete(name)
    except Exception:
        logger.warning("request_limits.store_unavailable", exc_info=True)
