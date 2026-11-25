import socket
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.system_intelligence.services.agents.providers import endpoints
from apps.system_intelligence.services.agents.providers.endpoints import (
    MAX_URL_CHARS,
    NEEDS_HTTPS,
    NO_CREDENTIALS,
    NO_HOST,
    PRIVATE_HOST,
    TOO_LONG,
    UNRESOLVABLE,
    EndpointError,
    ensure_public_host,
    validate_base_url,
)

GETADDRINFO = "apps.system_intelligence.services.agents.providers.endpoints.socket.getaddrinfo"


def _infos(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


class ValidateBaseUrlTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def assert_refused(self, url, message):
        with self.assertRaises(EndpointError) as ctx:
            validate_base_url(url)
        self.assertEqual(str(ctx.exception), message)

    def test_accepts_public_https_url_and_strips_trailing_slashes_and_whitespace(self):
        self.assertEqual(validate_base_url("  https://gateway.example.com/v1/  "), "https://gateway.example.com/v1")
        self.assertEqual(validate_base_url("https://gateway.example.com//"), "https://gateway.example.com")
        self.assertEqual(
            validate_base_url("https://gateway.example.com:8443/v1"), "https://gateway.example.com:8443/v1"
        )

    def test_accepts_public_ip_literals(self):
        self.assertEqual(validate_base_url("https://8.8.8.8/v1"), "https://8.8.8.8/v1")
        self.assertEqual(validate_base_url("https://[2001:4860:4860::8888]/v1"), "https://[2001:4860:4860::8888]/v1")
        self.assertEqual(validate_base_url("https://[::ffff:8.8.8.8]"), "https://[::ffff:8.8.8.8]")

    def test_refuses_non_string_and_empty(self):
        for value in (None, 123, b"https://example.com", ""):
            with self.subTest(value=value):
                self.assert_refused(value, NEEDS_HTTPS)

    def test_refuses_too_long_url(self):
        url = "https://example.com/" + "a" * MAX_URL_CHARS
        self.assert_refused(url, TOO_LONG)

    def test_refuses_non_https_schemes(self):
        for url in ("http://example.com", "ftp://example.com", "example.com", "HTTPS-ish://example.com"):
            with self.subTest(url=url):
                self.assert_refused(url, NEEDS_HTTPS)

    def test_refuses_malformed_ports(self):
        for url in ("https://example.com:abc", "https://example.com:99999", "https://[::1"):
            with self.subTest(url=url):
                self.assert_refused(url, NO_HOST)

    def test_refuses_credentials_query_and_fragment(self):
        for url in (
            "https://user@example.com",
            "https://user:pass@example.com",
            "https://:pass@example.com",
            "https://@example.com",
            "https://example.com/v1?key=1",
            "https://example.com/v1#frag",
        ):
            with self.subTest(url=url):
                self.assert_refused(url, NO_CREDENTIALS)

    def test_refuses_missing_host(self):
        for url in ("https://", "https:///v1", "https://./v1"):
            with self.subTest(url=url):
                self.assert_refused(url, NO_HOST)

    def test_refuses_local_and_single_label_hosts(self):
        for url in (
            "https://localhost",
            "https://LOCALHOST./v1",
            "https://api.localhost",
            "https://printer.local",
            "https://metadata.google.internal",
            "https://box.localdomain",
            "https://router.home.arpa",
            "https://intranet",
            "https://2130706433",
        ):
            with self.subTest(url=url):
                self.assert_refused(url, PRIVATE_HOST)

    def test_refuses_private_loopback_link_local_and_multicast_literals(self):
        for url in (
            "https://127.0.0.1",
            "https://10.0.0.5",
            "https://192.168.1.1",
            "https://172.16.0.1",
            "https://169.254.169.254/latest",
            "https://100.64.0.1",
            "https://0.0.0.0",
            "https://224.0.0.1",
            "https://[::1]",
            "https://[fe80::1]",
            "https://[fe80::1%25eth0]",
            "https://[fc00::1]",
            "https://[ff0e::1]",
            "https://[::ffff:127.0.0.1]",
            "https://[::ffff:169.254.169.254]",
            "https://[::ffff:10.0.0.1]",
        ):
            with self.subTest(url=url):
                self.assert_refused(url, PRIVATE_HOST)

    def test_is_public_rejects_non_ip_text(self):
        self.assertFalse(endpoints._is_public("not-an-ip"))
        self.assertTrue(endpoints._is_public("8.8.8.8"))
        self.assertFalse(endpoints._is_public("fe80::1%eth0"))


class EnsurePublicHostTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch(GETADDRINFO, return_value=_infos("8.8.8.8", "2001:4860:4860::8888"))
    def test_public_addresses_pass_and_default_port_is_443(self, getaddrinfo):
        self.assertIsNone(ensure_public_host("https://gateway.example.com/v1"))
        getaddrinfo.assert_called_once_with("gateway.example.com", 443, type=socket.SOCK_STREAM)

    @patch(GETADDRINFO, return_value=_infos("8.8.8.8"))
    def test_explicit_port_is_resolved(self, getaddrinfo):
        ensure_public_host("https://gateway.example.com:8443")
        getaddrinfo.assert_called_once_with("gateway.example.com", 8443, type=socket.SOCK_STREAM)

    @patch(GETADDRINFO, return_value=_infos("8.8.8.8", "10.0.0.7"))
    def test_any_private_address_refuses(self, _getaddrinfo):
        with self.assertRaises(EndpointError) as ctx:
            ensure_public_host("https://gateway.example.com")
        self.assertEqual(str(ctx.exception), PRIVATE_HOST)

    @patch(GETADDRINFO, return_value=_infos("169.254.169.254"))
    def test_metadata_address_refuses(self, _getaddrinfo):
        with self.assertRaisesMessage(EndpointError, PRIVATE_HOST):
            ensure_public_host("https://rebind.example.com")

    @patch(GETADDRINFO, return_value=[])
    def test_no_addresses_refuses(self, _getaddrinfo):
        with self.assertRaisesMessage(EndpointError, PRIVATE_HOST):
            ensure_public_host("https://gateway.example.com")

    def test_resolution_errors_are_unresolvable(self):
        for error in (socket.gaierror(socket.EAI_NONAME, "nope"), OSError("down"), UnicodeError("idna")):
            with self.subTest(error=type(error).__name__), patch(GETADDRINFO, side_effect=error):
                with self.assertRaises(EndpointError) as ctx:
                    ensure_public_host("https://gateway.example.com")
                self.assertEqual(str(ctx.exception), UNRESOLVABLE)
                self.assertIsNone(ctx.exception.__cause__)

    @patch(GETADDRINFO)
    def test_invalid_url_is_refused_before_any_lookup(self, getaddrinfo):
        with self.assertRaisesMessage(EndpointError, NEEDS_HTTPS):
            ensure_public_host("http://gateway.example.com")
        getaddrinfo.assert_not_called()
