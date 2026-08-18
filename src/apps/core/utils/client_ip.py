"""Originating-client IP resolution.

Behind the ALB every request's ``REMOTE_ADDR`` is the load balancer, so any per-client counter keyed on
it is really one global counter. ``NUM_PROXIES`` (set to 1 in production for exactly this reason) says
how many trailing ``X-Forwarded-For`` entries are trusted proxy hops.
"""

import hashlib

from django.conf import settings


def client_ip(request) -> str | None:
    """Return the originating client IP, honouring ``NUM_PROXIES`` trusted hops.

    ``X-Forwarded-For`` is appended to by each proxy, so with ``NUM_PROXIES = N`` the rightmost N
    entries are proxies and the Nth-from-right entry is the real client. ``NUM_PROXIES = 0`` trusts
    no XFF entry and uses ``REMOTE_ADDR`` (DRF semantics). Without ``NUM_PROXIES`` (dev / tests)
    fall back to the leftmost entry, then to ``REMOTE_ADDR``.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            num_proxies = getattr(settings, "NUM_PROXIES", None)
            if num_proxies is not None:
                if num_proxies == 0:
                    return request.META.get("REMOTE_ADDR")
                index = max(0, len(parts) - num_proxies)
                return parts[index]
            return parts[0]
    return request.META.get("REMOTE_ADDR")


def hash_ip(ip: str) -> str:
    """Salted SHA-256 hash of an IP. Salted with SECRET_KEY (repo convention)."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()
