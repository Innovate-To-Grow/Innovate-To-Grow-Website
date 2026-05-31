"""Tests for the page-freeze service: SSRF guard, fetch, inline, strip, orchestrate."""

import base64
import socket
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from apps.cms.services.freeze import BlockedURLError, FreezeError, FreezeFetchError, freeze_url
from apps.cms.services.freeze.cache import ResourceCache
from apps.cms.services.freeze.inliner import Inliner
from apps.cms.services.freeze.ssrf import guarded_get, validate_fetch_url
from apps.cms.services.freeze.strip import apply_removals, serialize, strip_scripts_and_handlers


class FakeResponse:
    def __init__(self, content=b"", *, status_code=200, headers=None, url="https://example.com/"):
        self._content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url
        self.encoding = None

    @property
    def apparent_encoding(self):
        return "utf-8"

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._content.decode(self.encoding or "utf-8", errors="replace")

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]

    def close(self):
        pass


class FakeSession:
    def __init__(self, route):
        self._route = route  # callable(url) -> FakeResponse (may raise)
        self.headers = {}
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        return self._route(url)

    def close(self):
        pass


def public_getaddrinfo(host, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def make_getaddrinfo(mapping):
    def _resolve(host, *args, **kwargs):
        ip = mapping.get(host, "93.184.216.34")
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _resolve


class FakeCache:
    def __init__(self, resources):
        self.resources = resources  # url -> (content_type, bytes)

    def fetch(self, url):
        if url not in self.resources:
            raise ValueError(f"missing {url}")
        return self.resources[url]

    def fetch_base64(self, url):
        ct, content = self.fetch(url)
        return f"data:{ct};base64,{base64.b64encode(content).decode()}"


class SsrfValidateTests(SimpleTestCase):
    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_accepts_public_https(self):
        self.assertEqual(validate_fetch_url("https://example.com/x"), "https://example.com/x")

    def test_rejects_non_http_schemes(self):
        for url in ["ftp://example.com/", "file:///etc/passwd", "javascript:alert(1)"]:
            with self.assertRaises(BlockedURLError):
                validate_fetch_url(url)

    def test_rejects_missing_host(self):
        with self.assertRaises(BlockedURLError):
            validate_fetch_url("http:///nohost")

    def test_rejects_internal_addresses(self):
        cases = {
            "loop.test": "127.0.0.1",
            "ten.test": "10.0.0.5",
            "oneninetwo.test": "192.168.1.1",
            "meta.test": "169.254.169.254",
            "v6loop.test": "::1",
        }
        for host, ip in cases.items():
            with patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=make_getaddrinfo({host: ip})):
                with self.assertRaises(BlockedURLError):
                    validate_fetch_url(f"http://{host}/")

    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo")
    def test_rejects_unresolvable_host(self, mock_gai):
        mock_gai.side_effect = socket.gaierror("nope")
        with self.assertRaises(BlockedURLError):
            validate_fetch_url("http://nope.invalid/")


class GuardedGetTests(SimpleTestCase):
    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_follows_redirect_and_returns_body(self):
        def route(url):
            if url == "https://a.test/":
                return FakeResponse(status_code=302, headers={"Location": "https://b.test/final"}, url=url)
            return FakeResponse(b"OK", url=url)

        resp = guarded_get(FakeSession(route), "https://a.test/", timeout=5, max_bytes=1000)
        self.assertEqual(resp.content, b"OK")

    def test_blocks_redirect_to_private(self):
        def route(url):
            return FakeResponse(status_code=302, headers={"Location": "http://evil.internal/"}, url=url)

        gai = make_getaddrinfo({"evil.internal": "10.0.0.1"})
        with patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=gai):
            with self.assertRaises(BlockedURLError):
                guarded_get(FakeSession(route), "https://a.test/", timeout=5, max_bytes=1000)

    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_enforces_size_via_content_length(self):
        def route(url):
            return FakeResponse(b"x" * 100, headers={"Content-Length": "100"}, url=url)

        with self.assertRaises(BlockedURLError):
            guarded_get(FakeSession(route), "https://a.test/", timeout=5, max_bytes=10)

    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_enforces_size_via_stream(self):
        def route(url):
            return FakeResponse(b"x" * 100, url=url)  # no Content-Length header

        with self.assertRaises(BlockedURLError):
            guarded_get(FakeSession(route), "https://a.test/", timeout=5, max_bytes=10)

    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_too_many_redirects(self):
        def route(url):
            return FakeResponse(status_code=302, headers={"Location": "https://a.test/next"}, url=url)

        with self.assertRaises(BlockedURLError):
            guarded_get(FakeSession(route), "https://a.test/", timeout=5, max_bytes=1000)

    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_redirect_without_location_raises(self):
        def route(url):
            return FakeResponse(status_code=302, headers={}, url=url)

        with self.assertRaises(BlockedURLError):
            guarded_get(FakeSession(route), "https://a.test/", timeout=5, max_bytes=1000)


class StripTests(SimpleTestCase):
    def test_strips_scripts_noscript_and_handlers(self):
        soup = BeautifulSoup(
            '<div onclick="x()"><script>evil()</script><noscript>n</noscript><p>hi</p></div>',
            "html.parser",
        )
        strip_scripts_and_handlers(soup)
        html = str(soup)
        self.assertNotIn("<script", html)
        self.assertNotIn("<noscript", html)
        self.assertNotIn("onclick", html)
        self.assertIn("<p>hi</p>", html)

    def test_strips_preload_and_meta_refresh(self):
        soup = BeautifulSoup(
            '<head><link rel="preload" href="x.js"><meta http-equiv="refresh" content="0;url=/y"></head>',
            "html.parser",
        )
        strip_scripts_and_handlers(soup)
        html = str(soup)
        self.assertNotIn("preload", html)
        self.assertNotIn("refresh", html)

    def test_apply_removals_presets_and_extra(self):
        soup = BeautifulSoup(
            "<header>H</header><div class='cookie-banner'>C</div><p class='keep'>K</p><aside class='x'>A</aside>",
            "html.parser",
        )
        apply_removals(soup, remove_presets=("header", "cookie_consent"), extra_selectors=[".x", "  "])
        html = str(soup)
        self.assertNotIn("<header", html)
        self.assertNotIn("cookie-banner", html)
        self.assertNotIn("<aside", html)
        self.assertIn("keep", html)

    def test_apply_removals_bad_selector_raises(self):
        soup = BeautifulSoup("<p>x</p>", "html.parser")
        with self.assertRaises(FreezeError):
            apply_removals(soup, extra_selectors=["((("])

    def test_serialize_adds_doctype_and_preserves_css(self):
        soup = BeautifulSoup(
            "<html><head><style>.a > .b{color:red}</style></head><body></body></html>",
            "html.parser",
        )
        out = serialize(soup)
        self.assertTrue(out.lstrip().lower().startswith("<!doctype"))
        self.assertIn(".a > .b", out)  # combinator preserved, not escaped


class InlinerTests(SimpleTestCase):
    def test_converts_link_to_style(self):
        cache = FakeCache({"https://x.test/s.css": ("text/css", b".a{color:red}")})
        soup = BeautifulSoup('<head><link rel="stylesheet" href="https://x.test/s.css"></head>', "html.parser")
        Inliner(cache).process_soup(soup, "https://x.test/")
        html = str(soup)
        self.assertNotIn("<link", html)
        self.assertIn("<style", html)
        self.assertIn(".a{color:red}", html)

    def test_inlines_css_import_and_url(self):
        cache = FakeCache(
            {
                "https://x.test/base.css": ("text/css", b"body{background:url('bg.png')}"),
                "https://x.test/bg.png": ("image/png", b"PNGDATA"),
            }
        )
        soup = BeautifulSoup('<style>@import "https://x.test/base.css";</style>', "html.parser")
        Inliner(cache).process_soup(soup, "https://x.test/")
        html = str(soup)
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn("@import", html)

    def test_inlines_img_and_strips_lazy_attrs(self):
        cache = FakeCache({"https://x.test/p.jpg": ("image/jpeg", b"JPG")})
        soup = BeautifulSoup('<img data-src="https://x.test/p.jpg" srcset="a 1x" loading="lazy">', "html.parser")
        Inliner(cache).process_soup(soup, "https://x.test/")
        html = str(soup)
        self.assertIn("data:image/jpeg;base64,", html)
        self.assertNotIn("srcset", html)
        self.assertNotIn("loading", html)
        self.assertNotIn("data-src", html)

    def test_skips_failed_resources_without_raising(self):
        cache = FakeCache({})  # nothing resolves
        soup = BeautifulSoup(
            '<link rel="stylesheet" href="https://x.test/missing.css"><img src="https://x.test/missing.png">',
            "html.parser",
        )
        Inliner(cache).process_soup(soup, "https://x.test/")  # must not raise


class ResourceCacheTests(SimpleTestCase):
    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_fetch_caches_and_base64(self):
        calls = []

        def route(url):
            calls.append(url)
            return FakeResponse(b"PNG", headers={"Content-Type": "image/png"}, url=url)

        cache = ResourceCache(FakeSession(route))
        ct, content = cache.fetch("https://x.test/a.png")
        self.assertEqual(ct, "image/png")
        self.assertEqual(content, b"PNG")
        cache.fetch("https://x.test/a.png")  # served from cache
        self.assertEqual(len(calls), 1)
        self.assertTrue(cache.fetch_base64("https://x.test/a.png").startswith("data:image/png;base64,"))

    @patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo)
    def test_fetch_http_error_raises(self):
        cache = ResourceCache(FakeSession(lambda url: FakeResponse(b"", status_code=404, url=url)))
        with self.assertRaises(ValueError):
            cache.fetch("https://x.test/missing.png")


class FreezeUrlTests(SimpleTestCase):
    def _run(self, html, **kwargs):
        session = FakeSession(lambda url: FakeResponse(html.encode("utf-8"), url=url))
        with (
            patch("apps.cms.services.freeze.orchestrator.requests.Session", return_value=session),
            patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo),
        ):
            return freeze_url("https://example.com/", **kwargs)

    def test_freezes_strips_and_keeps_css(self):
        html = (
            "<html><head><title>Hi</title><style>.a > .b{color:red}</style>"
            "<script>evil()</script></head><body><header>H</header><p>Body</p></body></html>"
        )
        result = self._run(html, remove_presets=("header",))
        self.assertEqual(result.title, "Hi")
        self.assertNotIn("<script", result.html)
        self.assertNotIn("<header", result.html)
        self.assertIn(".a > .b", result.html)
        self.assertIn("Body", result.html)
        self.assertGreater(result.byte_size, 0)
        self.assertTrue(result.html.lstrip().lower().startswith("<!doctype"))

    def test_oversize_raises(self):
        html = "<html><body>" + ("x" * 50) + "</body></html>"
        with patch("apps.cms.services.freeze.orchestrator.MAX_TOTAL_FROZEN_BYTES", 5):
            with self.assertRaises(FreezeError):
                self._run(html)

    def test_fetch_error_translates_to_freeze_fetch_error(self):
        def boom(url):
            raise ConnectionError("down")

        session = FakeSession(boom)
        with (
            patch("apps.cms.services.freeze.orchestrator.requests.Session", return_value=session),
            patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo),
        ):
            with self.assertRaises(FreezeFetchError):
                freeze_url("https://example.com/")

    def test_http_error_status_raises(self):
        session = FakeSession(lambda url: FakeResponse(b"nope", status_code=500, url=url))
        with (
            patch("apps.cms.services.freeze.orchestrator.requests.Session", return_value=session),
            patch("apps.cms.services.freeze.ssrf.socket.getaddrinfo", new=public_getaddrinfo),
        ):
            with self.assertRaises(FreezeFetchError):
                freeze_url("https://example.com/")

    def test_blocked_url_propagates(self):
        with patch(
            "apps.cms.services.freeze.ssrf.socket.getaddrinfo",
            new=make_getaddrinfo({"example.com": "10.0.0.9"}),
        ):
            with self.assertRaises(BlockedURLError):
                freeze_url("https://example.com/")
