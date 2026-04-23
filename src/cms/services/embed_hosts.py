"""Allowlist service for CMS `embed` block iframe sources.

Hosts come from the admin-managed `CMSEmbedAllowedHost` table. Entries may be
exact (`docs.google.com`) or subdomain wildcards (`*.youtube.com`). Lookups are
cached for a short TTL to keep block validation cheap.
"""

from urllib.parse import urlparse

from django.core.cache import cache

CACHE_KEY = "cms:embed-allowed-hosts:v1"
CACHE_TTL = 60


class InvalidEmbedURL(ValueError):
    """Raised when an embed src is missing, not https, or otherwise malformed."""


def parse_embed_url(src: str) -> tuple[str, str]:
    """Return `(scheme, host)` for a well-formed https embed URL.

    Raises `InvalidEmbedURL` if the URL is empty, relative, non-https, or has
    no host. The returned host is lowercase with any port stripped.
    """
    if not src or not isinstance(src, str):
        raise InvalidEmbedURL("Embed 'src' is required.")

    parsed = urlparse(src.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme != "https":
        raise InvalidEmbedURL("Embed 'src' must use https.")

    host = (parsed.hostname or "").lower()
    if not host:
        raise InvalidEmbedURL("Embed 'src' must include a host.")

    return scheme, host


def get_allowed_hosts() -> list[str]:
    """Return the list of active allowed hostnames (cached)."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    from cms.models import CMSEmbedAllowedHost

    hosts = list(CMSEmbedAllowedHost.objects.filter(is_active=True).values_list("hostname", flat=True))
    cache.set(CACHE_KEY, hosts, CACHE_TTL)
    return hosts


def invalidate_cache() -> None:
    cache.delete(CACHE_KEY)


def is_host_allowed(host: str) -> bool:
    """Return True if `host` matches any active entry (exact or wildcard)."""
    host = (host or "").lower()
    if not host:
        return False
    for entry in get_allowed_hosts():
        entry = entry.lower()
        if entry.startswith("*."):
            base = entry[2:]
            if host == base or host.endswith("." + base):
                return True
        elif host == entry:
            return True
    return False
