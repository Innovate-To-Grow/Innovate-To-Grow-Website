from unittest.mock import patch

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from apps.core.legacy_view.content.html_rewriting import rewrite_legacy_html
from apps.core.legacy_view.content.link_rewriting import (
    InvalidLegacyURL,
    RewrittenURL,
    rewrite_document_url,
    rewrite_location,
)
from apps.core.tests.web.legacy_view.rewriting.test_rewriting import ORIGIN_HOST, VIEWER_URL


class LegacyURLRewritingEdgeCaseTest(SimpleTestCase):
    def rewrite(self, value, current_path="/about"):
        return rewrite_document_url(value, current_path, ORIGIN_HOST, VIEWER_URL)

    def test_empty_and_fragment_only_urls_are_left_untouched(self):
        for value in ("", "   ", "#section"):
            with self.subTest(value=value):
                rewritten = self.rewrite(value)
                self.assertEqual(rewritten.value, value)
                self.assertFalse(rewritten.blocked)
                self.assertFalse(rewritten.internal)

    def test_script_scheme_urls_are_blocked(self):
        for value in ("javascript:alert(1)", " JavaScript:alert(1)", "vbscript:msgbox(1)"):
            with self.subTest(value=value):
                self.assertEqual(self.rewrite(value), RewrittenURL("#", blocked=True))

    def test_non_http_schemes_pass_through_as_external(self):
        for value in ("mailto:i2g@ucmerced.edu", "tel:+12095550100", "data:image/png;base64,AAAA"):
            with self.subTest(value=value):
                self.assertEqual(self.rewrite(value), RewrittenURL(value))

    def test_malformed_url_is_blocked_instead_of_raising(self):
        self.assertEqual(self.rewrite("http://[broken"), RewrittenURL("#", blocked=True))

    def test_failure_while_resolving_relative_url_is_blocked(self):
        with patch("apps.core.legacy_view.content.link_rewriting.urljoin", side_effect=ValueError("bad")):
            self.assertEqual(self.rewrite("/about"), RewrittenURL("#", blocked=True))

    def test_internal_url_with_encoded_traversal_is_blocked_as_internal(self):
        for value in ("/static/%2e%2e/admin", "http://172.31.69.63:8080/static%2F%2Fx"):
            with self.subTest(value=value):
                self.assertEqual(self.rewrite(value), RewrittenURL("#", blocked=True, internal=True))

    def test_internal_url_with_malformed_utf8_is_blocked_without_breaking_the_page(self):
        for value in ("/static/%FF", "/static/%25FF", "/about/%C3%28"):
            with self.subTest(value=value):
                self.assertEqual(self.rewrite(value), RewrittenURL("#", blocked=True, internal=True))

    def test_private_origin_and_public_hosts_are_rewritten_to_viewer_with_filtered_query(self):
        for value in (
            "http://172.31.69.63:8080/past-projects?page=2&token=secret",
            "https://35.86.48.145/past-projects?page=2&token=secret",
            "past-projects?page=2&token=secret",
        ):
            with self.subTest(value=value):
                rewritten = self.rewrite(value, current_path="/")
                self.assertEqual(rewritten, RewrittenURL(f"{VIEWER_URL}/past-projects?page=2", internal=True))
                self.assertNotIn(ORIGIN_HOST, rewritten.value)
                self.assertNotIn("token", rewritten.value)


class LegacyLocationRewritingEdgeCaseTest(SimpleTestCase):
    def location(self, value):
        return rewrite_location(value, "/about", ORIGIN_HOST, VIEWER_URL)

    def test_script_scheme_redirect_falls_back_to_viewer_root(self):
        self.assertEqual(self.location("javascript:alert(1)"), VIEWER_URL)

    def test_non_http_external_redirect_falls_back_to_viewer_root(self):
        self.assertEqual(self.location("mailto:i2g@ucmerced.edu"), VIEWER_URL)
        self.assertEqual(self.location("ftp://files.example.com/x"), VIEWER_URL)

    def test_external_redirect_that_only_parses_after_stripping_is_rejected(self):
        with self.assertRaises(InvalidLegacyURL):
            self.location("http://[::1] ")

    def test_internal_redirect_with_ambiguous_path_falls_back_to_viewer_root(self):
        self.assertEqual(self.location("http://172.31.69.63:8080/static/%2e%2e/admin"), VIEWER_URL)

    def test_internal_redirect_with_malformed_utf8_falls_back_to_viewer_root(self):
        self.assertEqual(self.location("http://172.31.69.63:8080/static/%FF"), VIEWER_URL)

    def test_private_origin_redirect_never_leaks_origin(self):
        location = self.location("http://172.31.69.63:8080/past-projects?page=3&code=secret#top")

        self.assertEqual(location, f"{VIEWER_URL}/past-projects?page=3#top")
        self.assertNotIn("8080", location)


class LegacyHTMLRewritingEdgeCaseTest(SimpleTestCase):
    def rewrite(self, html, current_path="/about"):
        return BeautifulSoup(rewrite_legacy_html(html, current_path, ORIGIN_HOST, VIEWER_URL), "html.parser")

    def test_srcset_keeps_rewritten_candidates_and_drops_blocked_ones(self):
        soup = self.rewrite(
            '<html><body><img id="mixed" srcset="/static/a.png 1x, , /admin/b.png 2x, '
            'https://cdn.example.com/c.png 3x"></body></html>'
        )

        self.assertEqual(
            soup.select_one("#mixed")["srcset"],
            f"{VIEWER_URL}/static/a.png 1x, https://cdn.example.com/c.png 3x",
        )

    def test_srcset_with_only_blocked_candidates_is_removed(self):
        soup = self.rewrite(
            '<html><body><picture><source id="src" srcset="/admin/a.png 1x, javascript:alert(1) 2x">'
            "</picture></body></html>"
        )

        self.assertNotIn("srcset", soup.select_one("#src").attrs)

    def test_blocked_links_lose_event_handlers_and_blocked_media_lose_src(self):
        soup = self.rewrite(
            "<html><body>"
            '<a id="js" href="javascript:doIt()" onclick="doIt()" onMouseOver="track()">Run</a>'
            '<a id="anchor" name="top">Top</a>'
            '<img id="img" src="/admin/secret.png" alt="x">'
            '<iframe id="frame" src="/signup"></iframe>'
            "</body></html>"
        )

        link = soup.select_one("#js")
        self.assertEqual(link["href"], "#")
        self.assertEqual(link["tabindex"], "-1")
        self.assertNotIn("onclick", link.attrs)
        self.assertNotIn("onmouseover", link.attrs)
        self.assertNotIn("href", soup.select_one("#anchor").attrs)
        self.assertNotIn("src", soup.select_one("#img").attrs)
        self.assertEqual(soup.select_one("#img")["alt"], "x")
        self.assertNotIn("src", soup.select_one("#frame").attrs)

    def test_fragment_without_body_still_gets_banner_first(self):
        soup = self.rewrite('<p>Archived</p><a href="http://172.31.69.63:8080/about">About</a>')

        first = soup.find(recursive=False)
        self.assertEqual(first["id"], "i2g-legacy-read-only-banner")
        self.assertEqual(soup.a["href"], f"{VIEWER_URL}/about")
        self.assertNotIn(ORIGIN_HOST, str(soup))
