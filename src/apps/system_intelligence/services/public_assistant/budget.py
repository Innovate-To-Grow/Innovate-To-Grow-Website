"""Per-IP token budgeting for the public assistant.

The budget is tracked entirely in Django's cache (LocMem in dev, Redis in
prod) as a rolling counter keyed on a salted SHA-256 hash of the client IP.
Only the hash is ever stored -- never the raw IP.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache

# Fallback window if a non-positive value is configured: in Django, a cache
# timeout of 0 means "expire immediately / do not store", which would silently
# disable the budget. Clamp to a 1-day rolling window instead.
_DEFAULT_WINDOW_SECONDS = 86400


def client_ip(request) -> str | None:
    """Return the originating client IP, honouring NUM_PROXIES trusted hops.

    Mirrors ``apps.cms.views.analytics.PageViewCreateView._get_client_ip``:
    X-Forwarded-For is appended-to by each proxy. With ``NUM_PROXIES = N`` the
    rightmost N entries are trusted proxy hops and the Nth-from-right entry is
    the actual client. Without NUM_PROXIES (dev / tests) fall back to the
    leftmost entry, then to REMOTE_ADDR.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            num_proxies = getattr(settings, "NUM_PROXIES", None)
            if num_proxies:
                index = max(0, len(parts) - num_proxies)
                return parts[index]
            return parts[0]
    return request.META.get("REMOTE_ADDR")


def hash_ip(ip: str) -> str:
    """Salted SHA-256 hash of an IP. Salt with SECRET_KEY (repo convention)."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()


def budget_key(ip_hash: str) -> str:
    return f"assistant:tokens:{ip_hash}"


def tokens_used(ip_hash: str) -> int:
    return cache.get(budget_key(ip_hash), 0)


def check_budget(ip_hash: str, limit: int) -> bool:
    """True if the IP may spend more tokens. limit <= 0 means unlimited."""
    if limit <= 0:
        return True
    return tokens_used(ip_hash) < limit


def record_usage(ip_hash: str, tokens: int, window_seconds: int) -> None:
    """Add ``tokens`` to the rolling per-IP counter, creating it if absent."""
    if tokens <= 0:
        return
    # A timeout of 0 (or negative) makes Django's cache discard the write
    # immediately, silently disabling the budget; clamp to a sane window.
    if window_seconds <= 0:
        window_seconds = _DEFAULT_WINDOW_SECONDS
    key = budget_key(ip_hash)
    # add() is a no-op if the key already exists, so the window is set on the
    # first write of the period and the counter rolls over when it expires.
    cache.add(key, 0, timeout=window_seconds)
    try:
        cache.incr(key, tokens)
    except ValueError:
        # The key expired between add() and incr(); re-seed and retry once.
        cache.add(key, 0, timeout=window_seconds)
        try:
            cache.incr(key, tokens)
        except ValueError:
            cache.set(key, tokens, timeout=window_seconds)
