"""Base-URL rules for Custom endpoint providers: https only, no credentials or query in the URL, and every address
the host resolves to must be public, so a stored API key can never be sent to the server's own network (the ECS
metadata endpoint, VPC hosts, loopback). Known presets are fixed public hosts and skip the DNS check.

The DNS check runs again before every call (``ensure_public_host``). A host that changes its answer between that
check and the connection (DNS rebinding) is not covered; admins who can add providers are trusted staff.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

MAX_URL_CHARS = 512
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")

NEEDS_HTTPS = "Use an https:// URL."
NO_HOST = "The URL needs a host name."
NO_CREDENTIALS = "Do not put a user name, password, query or fragment in the URL."
PRIVATE_HOST = "The host must be a public internet address, not a private, loopback or link-local one."
UNRESOLVABLE = "The provider's host name could not be resolved."
TOO_LONG = f"The URL may be at most {MAX_URL_CHARS} characters."


class EndpointError(ValueError):
    """A base URL that may not be called. The message is fixed text."""


def _is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


def validate_base_url(url) -> str:
    """Return the normalized URL (no trailing slash) or raise ``EndpointError``. No network access."""
    url = (url or "").strip() if isinstance(url, str) else ""
    if len(url) > MAX_URL_CHARS:
        raise EndpointError(TOO_LONG)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise EndpointError(NO_HOST) from None
    if parts.scheme != "https":
        raise EndpointError(NEEDS_HTTPS)
    if parts.username or parts.password or parts.query or parts.fragment or "@" in parts.netloc:
        raise EndpointError(NO_CREDENTIALS)
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise EndpointError(NO_HOST)
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES) or "." not in host and ":" not in host:
        raise EndpointError(PRIVATE_HOST)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not _is_public(host):
            raise EndpointError(PRIVATE_HOST)
    del port  # parsed only to reject malformed ports
    return url.rstrip("/")


def ensure_public_host(url: str) -> None:
    """Resolve the URL's host and refuse it unless every address is public. Raises ``EndpointError``."""
    parts = urlsplit(validate_base_url(url))
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise EndpointError(UNRESOLVABLE) from None
    addresses = {info[4][0] for info in infos}
    if not addresses or not all(_is_public(address) for address in addresses):
        raise EndpointError(PRIVATE_HOST)
