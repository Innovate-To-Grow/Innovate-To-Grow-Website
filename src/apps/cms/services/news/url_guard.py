"""SSRF guard for outbound news fetches.

The news sync fetches a feed URL (admin-configurable on ``NewsFeedSource``) and
then scrapes every article URL taken from that feed's ``<link>`` elements. Both
inputs cross a trust boundary — a CMS-scoped staff editor controls the feed URL,
and the remote feed controls the article links — so neither may be handed to
``urlopen`` unchecked. Without this guard an editor (or a malicious feed) could
reach internal services (``http://169.254.169.254/`` metadata, RFC1918 hosts) or
read local files (``file:///etc/passwd``), turning content-editor access into a
network/host primitive.

``safe_urlopen`` is the only sanctioned way to fetch these URLs. It:
  * enforces an http/https scheme allowlist and rejects embedded credentials;
  * resolves the host and **connects to the exact validated IP** — the socket is
    pinned to an address that was checked against the blocked ranges in the same
    ``getaddrinfo`` result, so there is no resolve-then-reconnect window for DNS
    rebinding (the connect target is a literal IP, never re-resolved);
  * re-applies the same checks to every redirect target.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.request
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


class UnsafeUrlError(ValueError):
    """Raised when a URL is not allowed to be fetched (SSRF guard)."""


def has_allowed_scheme(url: str) -> bool:
    """True when ``url`` uses an http/https scheme (cheap, no DNS lookup)."""
    return urlsplit(url).scheme in _ALLOWED_SCHEMES


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) before classifying.
    if ip.version == 6 and ip.ipv4_mapped is not None:
        return _ip_is_blocked(ip.ipv4_mapped)
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def _resolve_ips(host: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def validate_public_http_url(url: str) -> str:
    """Return ``url`` unchanged if it is safe to fetch, else raise ``UnsafeUrlError``.

    Enforces the scheme allowlist, forbids userinfo credentials, and fails fast
    when the host resolves to a non-public address. This is a pre-flight check;
    the authoritative protection against DNS rebinding is the connect-time
    pinning in :func:`_guarded_create_connection`, which both the initial fetch
    and every redirect go through.
    """
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError("URL scheme must be http or https.")
    if parts.username or parts.password:
        raise UnsafeUrlError("URL must not contain credentials.")

    host = parts.hostname
    if not host:
        raise UnsafeUrlError("URL must include a host.")

    try:
        port = parts.port or _DEFAULT_PORTS[parts.scheme]
    except ValueError as exc:  # malformed port
        raise UnsafeUrlError("URL has an invalid port.") from exc

    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        ips = [literal_ip]
    else:
        try:
            ips = _resolve_ips(host, port)
        except OSError as exc:
            raise UnsafeUrlError(f"Could not resolve host: {host}") from exc

    if not ips:
        raise UnsafeUrlError(f"Could not resolve host: {host}")
    for ip in ips:
        if _ip_is_blocked(ip):
            raise UnsafeUrlError("URL resolves to a non-public address.")
    return url


def _guarded_create_connection(host, port, timeout, source_address):
    """Resolve ``host`` once, reject any non-public address, then connect to the
    exact resolved IP. Because the connect target is a numeric address (never the
    hostname), the kernel does not re-resolve — closing the validate/connect DNS
    rebinding window."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    validated: list[tuple] = []
    for _family, _socktype, _proto, _canonname, sockaddr in infos:
        if _ip_is_blocked(ipaddress.ip_address(sockaddr[0])):
            raise UnsafeUrlError("URL resolves to a non-public address.")
        validated.append(sockaddr)

    last_err: Exception | None = None
    for sockaddr in validated:
        ip_literal, conn_port = sockaddr[0], sockaddr[1]
        try:
            # ip_literal is numeric => create_connection's getaddrinfo is a no-op
            # lookup of the literal, so the socket lands on the validated address.
            return socket.create_connection((ip_literal, conn_port), timeout, source_address)
        except OSError as exc:
            last_err = exc
    if last_err is not None:
        raise last_err
    raise UnsafeUrlError(f"Could not resolve host: {host}")


class _GuardedHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = _guarded_create_connection(self.host, self.port, self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()


class _GuardedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        sock = _guarded_create_connection(self.host, self.port, self.timeout, self.source_address)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            server_hostname = self._tunnel_host
        else:
            server_hostname = self.host
        # SNI / cert validation still use the original hostname, not the IP.
        self.sock = self._context.wrap_socket(sock, server_hostname=server_hostname)


class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_GuardedHTTPConnection, req)


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_GuardedHTTPSConnection, req, context=self._context)


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates every redirect target's scheme/host so a remote server cannot
    30x-bounce the request to a non-http scheme; the connection it produces is
    itself IP-pinned, so a rebinding redirect host is also blocked at connect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(url: str, *, timeout: float, headers: dict | None = None):
    """Validate ``url`` (and every redirect) then open it through IP-pinned
    connections. Mirrors ``urlopen``'s context-manager return so callers can
    ``with safe_urlopen(...) as resp:``."""
    validate_public_http_url(url)
    request = urllib.request.Request(url, headers=headers or {})
    opener = urllib.request.build_opener(
        _GuardedHTTPHandler(),
        _GuardedHTTPSHandler(),
        _ValidatingRedirectHandler(),
    )
    return opener.open(request, timeout=timeout)
