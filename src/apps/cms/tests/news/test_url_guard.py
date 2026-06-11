"""Regression tests for the news-fetch SSRF guard.

Covers the confirmed SSRF/file-read finding: feed and article URLs are fetched
with no scheme/host restriction, letting a CMS-scoped staff editor (or a
malicious remote feed) reach internal services or read local files.
"""

import ipaddress
import socket
import urllib.request
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.cms.services.news import url_guard
from apps.cms.services.news.url_guard import (
    UnsafeUrlError,
    _guarded_create_connection,
    _resolve_ips,
    has_allowed_scheme,
    safe_urlopen,
    validate_public_http_url,
)


def _ips(*addresses):
    return [ipaddress.ip_address(a) for a in addresses]


def _addrinfo(*addresses, port=443):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, port)) for addr in addresses]


class ValidatePublicHttpUrlTest(TestCase):
    @patch("apps.cms.services.news.url_guard._resolve_ips", return_value=_ips("93.184.216.34"))
    def test_allows_public_https_host(self, _resolve):
        self.assertEqual(
            validate_public_http_url("https://news.ucmerced.edu/feed"),
            "https://news.ucmerced.edu/feed",
        )

    def test_rejects_file_scheme(self):
        # The headline finding: file:///etc/passwd must never be fetchable.
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("file:///etc/passwd")

    def test_rejects_ftp_and_gopher_schemes(self):
        for url in ("ftp://example.com/x", "gopher://example.com/x", "data:text/plain,hi"):
            with self.assertRaises(UnsafeUrlError):
                validate_public_http_url(url)

    def test_rejects_link_local_metadata_ip(self):
        # AWS instance metadata endpoint.
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_loopback_ip(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://127.0.0.1:8000/admin/")

    def test_rejects_private_rfc1918_ip(self):
        for url in ("http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/"):
            with self.assertRaises(UnsafeUrlError):
                validate_public_http_url(url)

    def test_rejects_ipv4_mapped_ipv6_loopback(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://[::ffff:127.0.0.1]/")

    def test_rejects_embedded_credentials(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("https://user:pass@news.ucmerced.edu/feed")

    @patch("apps.cms.services.news.url_guard._resolve_ips", return_value=_ips("127.0.0.1"))
    def test_rejects_hostname_resolving_to_loopback(self, _resolve):
        # DNS-name pointing at an internal address (not just a literal IP).
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://internal.example/")

    @patch("apps.cms.services.news.url_guard._resolve_ips", return_value=_ips("203.0.113.10", "10.0.0.5"))
    def test_rejects_when_any_resolved_ip_is_private(self, _resolve):
        # A host that resolves to both a public and a private address is rejected.
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://split-horizon.example/")

    @patch("apps.cms.services.news.url_guard._resolve_ips", side_effect=OSError("no such host"))
    def test_rejects_unresolvable_host(self, _resolve):
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://does-not-resolve.invalid/")


class HasAllowedSchemeTest(TestCase):
    def test_true_for_http_and_https(self):
        self.assertTrue(has_allowed_scheme("http://x/"))
        self.assertTrue(has_allowed_scheme("https://x/"))

    def test_false_for_other_schemes(self):
        for url in ("file:///etc/passwd", "javascript:alert(1)", "ftp://x/", ""):
            self.assertFalse(has_allowed_scheme(url))


class SafeUrlopenRedirectGuardTest(TestCase):
    def test_redirect_to_internal_address_is_blocked(self):
        # An external server that 30x-bounces to the metadata endpoint must be
        # caught by the redirect re-validation, not followed.
        from apps.cms.services.news.url_guard import _ValidatingRedirectHandler

        handler = _ValidatingRedirectHandler()
        with self.assertRaises(UnsafeUrlError):
            handler.redirect_request(
                req=None,
                fp=None,
                code=302,
                msg="Found",
                headers={},
                newurl="http://169.254.169.254/latest/meta-data/",
            )

    @patch("apps.cms.services.news.url_guard.validate_public_http_url", side_effect=UnsafeUrlError("nope"))
    def test_safe_urlopen_validates_before_opening(self, mock_validate):
        with self.assertRaises(UnsafeUrlError):
            safe_urlopen("http://169.254.169.254/", timeout=5)
        mock_validate.assert_called_once()

    def test_safe_urlopen_uses_ip_pinning_handlers(self):
        # Structural guard: the opener must route through the IP-pinned
        # connection handlers and the redirect re-validator.
        with patch.object(url_guard, "validate_public_http_url", return_value="http://x/"):
            with patch("urllib.request.OpenerDirector.open", return_value=object()) as mock_open:
                with patch("urllib.request.build_opener", wraps=url_guard.urllib.request.build_opener) as mock_build:
                    safe_urlopen("http://example.com/", timeout=5)
        handler_types = {type(h).__name__ for h in mock_build.call_args[0]}
        assert "_GuardedHTTPHandler" in handler_types
        assert "_GuardedHTTPSHandler" in handler_types
        assert "_ValidatingRedirectHandler" in handler_types
        mock_open.assert_called_once()


class GuardedCreateConnectionTest(TestCase):
    """The connect-time pinning that actually defeats DNS rebinding: resolve
    once, reject non-public addresses, and connect to the literal IP."""

    def test_connects_to_the_exact_resolved_public_ip(self):
        sentinel = object()
        with patch("apps.cms.services.news.url_guard.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
            with patch("apps.cms.services.news.url_guard.socket.create_connection", return_value=sentinel) as mock_conn:
                sock = _guarded_create_connection("example.com", 443, 10, None)
        assert sock is sentinel
        # Pinned: connect target is the resolved numeric IP, never the hostname.
        mock_conn.assert_called_once_with(("93.184.216.34", 443), 10, None)

    def test_blocks_when_connect_time_resolution_returns_loopback(self):
        # The DNS-rebinding case: validation may have seen a public IP, but the
        # resolution at connect returns loopback. Pinning must block it and never
        # open a socket.
        with patch("apps.cms.services.news.url_guard.socket.getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            with patch("apps.cms.services.news.url_guard.socket.create_connection") as mock_conn:
                with self.assertRaises(UnsafeUrlError):
                    _guarded_create_connection("rebind.evil", 80, 10, None)
        mock_conn.assert_not_called()

    def test_blocks_metadata_endpoint_at_connect(self):
        with patch(
            "apps.cms.services.news.url_guard.socket.getaddrinfo", return_value=_addrinfo("169.254.169.254", port=80)
        ):
            with patch("apps.cms.services.news.url_guard.socket.create_connection") as mock_conn:
                with self.assertRaises(UnsafeUrlError):
                    _guarded_create_connection("metadata.example", 80, 10, None)
        mock_conn.assert_not_called()

    def test_full_rebinding_bypass_is_closed(self):
        # End-to-end of the reported bypass: validate() sees a public answer,
        # then the connect-time lookup flips to loopback. The pre-flight passes
        # but the pinned connect blocks — so the guard holds.
        with patch("apps.cms.services.news.url_guard._resolve_ips", return_value=_ips("93.184.216.34")):
            validate_public_http_url("http://rebind.evil/feed")  # pre-flight passes
        with patch("apps.cms.services.news.url_guard.socket.getaddrinfo", return_value=_addrinfo("127.0.0.1", port=80)):
            with self.assertRaises(UnsafeUrlError):
                _guarded_create_connection("rebind.evil", 80, 10, None)


class ResolveIpsTest(TestCase):
    def test_maps_getaddrinfo_results_to_ip_addresses(self):
        with patch(
            "apps.cms.services.news.url_guard.socket.getaddrinfo",
            return_value=_addrinfo("93.184.216.34", "203.0.113.5"),
        ) as mock_gai:
            ips = _resolve_ips("example.com", 443)
        self.assertEqual(ips, _ips("93.184.216.34", "203.0.113.5"))
        mock_gai.assert_called_once_with("example.com", 443, type=socket.SOCK_STREAM)


class ValidateEdgeCaseTest(TestCase):
    def test_rejects_url_without_host(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http:///just/a/path")

    def test_rejects_invalid_port(self):
        # Out-of-range port: SplitResult.port raises ValueError on access.
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://example.com:99999/")

    def test_rejects_host_with_no_dns_records(self):
        with patch("apps.cms.services.news.url_guard._resolve_ips", return_value=[]):
            with self.assertRaises(UnsafeUrlError):
                validate_public_http_url("http://no-records.example/")


class GuardedCreateConnectionErrorTest(TestCase):
    def test_reraises_last_os_error_when_every_address_refuses(self):
        # All validated addresses are public but each connect() fails; the last
        # OSError propagates rather than being swallowed.
        with patch(
            "apps.cms.services.news.url_guard.socket.getaddrinfo",
            return_value=_addrinfo("8.8.8.8", "1.1.1.1", port=80),
        ):
            with patch(
                "apps.cms.services.news.url_guard.socket.create_connection",
                side_effect=OSError("connection refused"),
            ) as mock_conn:
                with self.assertRaises(OSError):
                    _guarded_create_connection("example.com", 80, 10, None)
        self.assertEqual(mock_conn.call_count, 2)

    def test_raises_unsafe_when_resolution_is_empty(self):
        with patch("apps.cms.services.news.url_guard.socket.getaddrinfo", return_value=[]):
            with patch("apps.cms.services.news.url_guard.socket.create_connection") as mock_conn:
                with self.assertRaises(UnsafeUrlError):
                    _guarded_create_connection("example.com", 80, 10, None)
        mock_conn.assert_not_called()


class GuardedHTTPConnectionTest(TestCase):
    def test_connect_pins_socket_without_tunnel(self):
        conn = url_guard._GuardedHTTPConnection("example.com", 80)
        sentinel = object()
        with patch.object(url_guard, "_guarded_create_connection", return_value=sentinel) as gc:
            conn.connect()
        self.assertIs(conn.sock, sentinel)
        gc.assert_called_once_with(conn.host, conn.port, conn.timeout, conn.source_address)

    def test_connect_runs_tunnel_when_configured(self):
        conn = url_guard._GuardedHTTPConnection("example.com", 80)
        conn.set_tunnel("proxy.internal", 8080)
        with patch.object(url_guard, "_guarded_create_connection", return_value=object()):
            with patch.object(conn, "_tunnel") as tunnel:
                conn.connect()
        tunnel.assert_called_once()


class GuardedHTTPSConnectionTest(TestCase):
    def test_connect_wraps_socket_with_host_sni_without_tunnel(self):
        conn = url_guard._GuardedHTTPSConnection("example.com", 443)
        raw_sock, wrapped = object(), object()
        conn._context = MagicMock()
        conn._context.wrap_socket.return_value = wrapped
        with patch.object(url_guard, "_guarded_create_connection", return_value=raw_sock):
            conn.connect()
        self.assertIs(conn.sock, wrapped)
        conn._context.wrap_socket.assert_called_once_with(raw_sock, server_hostname="example.com")

    def test_connect_uses_tunnel_host_for_sni_when_tunneling(self):
        conn = url_guard._GuardedHTTPSConnection("example.com", 443)
        conn.set_tunnel("proxy.internal", 8080)
        raw_sock, wrapped = object(), object()
        conn._context = MagicMock()
        conn._context.wrap_socket.return_value = wrapped
        with patch.object(url_guard, "_guarded_create_connection", return_value=raw_sock):
            with patch.object(conn, "_tunnel") as tunnel:
                conn.connect()
        tunnel.assert_called_once()
        conn._context.wrap_socket.assert_called_once_with(raw_sock, server_hostname="proxy.internal")
        self.assertIs(conn.sock, wrapped)


class GuardedHandlerTest(TestCase):
    def test_http_handler_opens_with_pinned_connection_class(self):
        handler = url_guard._GuardedHTTPHandler()
        req = object()
        with patch.object(handler, "do_open", return_value="resp") as do_open:
            self.assertEqual(handler.http_open(req), "resp")
        do_open.assert_called_once_with(url_guard._GuardedHTTPConnection, req)

    def test_https_handler_opens_with_pinned_connection_class(self):
        handler = url_guard._GuardedHTTPSHandler()
        req = object()
        with patch.object(handler, "do_open", return_value="resp") as do_open:
            self.assertEqual(handler.https_open(req), "resp")
        do_open.assert_called_once_with(url_guard._GuardedHTTPSConnection, req, context=handler._context)

    def test_redirect_handler_delegates_after_validating_allowed_target(self):
        handler = url_guard._ValidatingRedirectHandler()
        with patch(
            "apps.cms.services.news.url_guard.validate_public_http_url", return_value="http://ok.example/"
        ) as validate:
            with patch.object(
                urllib.request.HTTPRedirectHandler, "redirect_request", return_value="REDIRECT"
            ) as parent:
                result = handler.redirect_request(
                    req="r", fp="f", code=302, msg="Found", headers={}, newurl="http://ok.example/"
                )
        self.assertEqual(result, "REDIRECT")
        validate.assert_called_once_with("http://ok.example/")
        parent.assert_called_once()
