"""SSRF protections for fetching admin-supplied external URLs.

Every outbound fetch in the freeze service routes through here: the initial
page, each redirect hop, and every sub-resource (CSS ``@import``, ``url()``,
``<link>``, ``<img>``). We refuse non-http(s) schemes and any host that
resolves to a private / loopback / link-local / reserved address — this covers
the cloud metadata endpoint ``169.254.169.254`` and IPv6 ``::1`` / ``fc00::/7``.

No SSRF guard existed in the codebase before this; admin-supplied URLs make it
load-bearing, so it is the single chokepoint for all freeze fetches.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

from .config import MAX_REDIRECTS, USER_AGENT

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class BlockedURLError(ValueError):
    """Raised when a URL is refused by the SSRF guard (scheme, host, or size)."""


def _ip_is_blocked(ip: IpAddress) -> bool:
    # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) so the checks below apply.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # 169.254.0.0/16 incl. the 169.254.169.254 metadata endpoint
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_addresses(host: str) -> list[IpAddress]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise BlockedURLError(f"Could not resolve host: {host}") from exc
    addresses: list[IpAddress] = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    if not addresses:
        raise BlockedURLError(f"Could not resolve host: {host}")
    return addresses


def validate_fetch_url(url: str) -> str:
    """Validate a URL for outbound fetching; return it unchanged or raise BlockedURLError."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise BlockedURLError(f"Unsupported URL scheme {parts.scheme or '(none)'!r}. Only http and https are allowed.")
    host = parts.hostname
    if not host:
        raise BlockedURLError("URL has no host.")
    # Reject if ANY resolved address is internal — defeats DNS round-robin tricks.
    for ip in _resolve_addresses(host):
        if _ip_is_blocked(ip):
            raise BlockedURLError(f"Host '{host}' resolves to a blocked internal address ({ip}).")
    return url


def _enforce_and_read(resp, max_bytes: int):
    """Cap the response body at ``max_bytes`` and materialize it on the Response."""
    declared = resp.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                resp.close()
                raise BlockedURLError(f"Resource exceeds size limit ({int(declared):,} > {max_bytes:,} bytes).")
        except ValueError:
            pass  # ignore a malformed Content-Length; the streamed cap below still applies
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            resp.close()
            raise BlockedURLError(f"Resource exceeds size limit (> {max_bytes:,} bytes).")
        chunks.append(chunk)
    resp._content = b"".join(chunks)
    resp._content_consumed = True
    return resp


def guarded_get(session, url: str, *, timeout: int, max_bytes: int, headers: dict | None = None):
    """GET a URL through the SSRF guard, following redirects manually with re-validation.

    Returns a fully-read ``requests.Response`` (body capped at ``max_bytes``).
    Raises BlockedURLError if the URL — or any redirect hop — is rejected.
    """
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)

    current = url
    for _ in range(MAX_REDIRECTS + 1):
        validate_fetch_url(current)
        resp = session.get(current, headers=request_headers, timeout=timeout, allow_redirects=False, stream=True)
        if resp.status_code in _REDIRECT_STATUSES:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise BlockedURLError("Redirect response had no Location header.")
            current = urljoin(current, location)
            continue
        return _enforce_and_read(resp, max_bytes)
    raise BlockedURLError(f"Too many redirects (>{MAX_REDIRECTS}).")
