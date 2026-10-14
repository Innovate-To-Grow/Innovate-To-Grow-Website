from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from apps.core.legacy_view.rewriting import (
    InvalidLegacyURL,
    RewrittenURL,
    rewrite_document_url,
    rewrite_legacy_html,
    rewrite_location,
)
from apps.core.legacy_view.views import _LEGACY_CSP

VIEWER_URL = "https://d111111abcdef8.cloudfront.net"
ORIGIN_HOST = "172.31.69.63"
ARCHIVE_PATH = Path(__file__).resolve().parents[5] / "archive" / "legacy" / "webpages.zip"


def archived_source(member: str) -> str:
    with ZipFile(ARCHIVE_PATH) as archive:
        return archive.read(f"webpages/project/{member}").decode("utf-8")


class LegacyHTMLRewritingTest(SimpleTestCase):
    def test_rewrites_safe_internal_links_and_disables_unknown_or_write_links(self):
        rewritten = rewrite_legacy_html(
            """
            <html><head><base href="https://legacy.i2g.ucmerced.edu/">
              <meta http-equiv="refresh" content="0; /admin/"></head>
            <body>
              <a id="safe" href="/about?q=history#team">About</a>
              <a id="write" href="https://legacy.i2g.ucmerced.edu/update/token">Update</a>
              <a id="unknown" href="/unreviewed">Unknown</a>
              <a id="external" href="https://www.ucmerced.edu/">UCM</a>
              <img id="image" src="/static/images/i2glogo.png">
              <script id="tracker" src="/static/js/js-siteimprove.js"></script>
            </body></html>
            """,
            "/about",
            ORIGIN_HOST,
            VIEWER_URL,
        )
        soup = BeautifulSoup(rewritten, "html.parser")

        self.assertIsNone(soup.find("base"))
        self.assertIsNone(soup.find("meta", attrs={"http-equiv": "refresh"}))
        self.assertEqual(soup.select_one("#safe")["href"], f"{VIEWER_URL}/about?q=history#team")
        self.assertEqual(soup.select_one("#external")["href"], "https://www.ucmerced.edu/")
        self.assertEqual(soup.select_one("#image")["src"], f"{VIEWER_URL}/static/images/i2glogo.png")
        self.assertIsNone(soup.select_one("#tracker"))
        for selector in ("#write", "#unknown"):
            link = soup.select_one(selector)
            self.assertEqual(link["href"], "#")
            self.assertEqual(link["aria-disabled"], "true")
            self.assertEqual(link["data-legacy-write-disabled"], "true")

    def test_injects_banner_and_disables_every_form_control(self):
        rewritten = rewrite_legacy_html(
            """
            <html><body><form action="/past-projects" method="post" onsubmit="submitIt()">
              <input name="team"><select><option>One</option></select><textarea></textarea><button>Save</button>
            </form></body></html>
            """,
            "/past-projects",
            ORIGIN_HOST,
            VIEWER_URL,
        )
        soup = BeautifulSoup(rewritten, "html.parser")
        banner = soup.body.find(recursive=False)

        self.assertEqual(banner["id"], "i2g-legacy-read-only-banner")
        self.assertIn("Legacy read-only", banner.get_text())
        form = soup.form
        self.assertEqual(form["action"], "#")
        self.assertEqual(form["method"], "get")
        self.assertIn("inert", form.attrs)
        self.assertNotIn("onsubmit", form.attrs)
        for control in form.find_all(["input", "select", "option", "textarea", "button"]):
            self.assertIn("disabled", control.attrs)

    def test_archived_mobile_navigation_button_remains_usable(self):
        archived_nav = BeautifulSoup(archived_source("templates/includes/nav.html"), "html.parser")
        nav_button = archived_nav.select_one("button.btn-navbar")
        self.assertIsNotNone(nav_button)

        rewritten = rewrite_legacy_html(f"<body>{nav_button}</body>", "/about", ORIGIN_HOST, VIEWER_URL)
        button = BeautifulSoup(rewritten, "html.parser").select_one("button.btn-navbar")

        self.assertNotIn("disabled", button.attrs)
        self.assertEqual(button["data-toggle"], "collapse")
        self.assertEqual(button["data-target"], ".nav-collapse")

    def test_archived_past_project_local_controls_work_but_share_stays_disabled(self):
        archived_page = BeautifulSoup(archived_source("templates/home/past-projects.html"), "html.parser")
        controls = archived_page.select_one(".buttonStick")
        self.assertIsNotNone(controls)

        rewritten = rewrite_legacy_html(f"<body>{controls}</body>", "/past-projects", ORIGIN_HOST, VIEWER_URL)
        soup = BeautifulSoup(rewritten, "html.parser")

        for selector in ("button.addtable", "button.merge", "button.deleterow", "button.keeprow", "#tabledelete"):
            with self.subTest(selector=selector):
                self.assertNotIn("disabled", soup.select_one(selector).attrs)
        share = soup.select_one("#share")
        self.assertIn("disabled", share.attrs)
        self.assertIn("inert", share.find_parent("form").attrs)
        self.assertEqual(share.find_parent("form")["action"], "#")

        other_page = BeautifulSoup(
            rewrite_legacy_html(f"<body>{controls}</body>", "/about", ORIGIN_HOST, VIEWER_URL), "html.parser"
        )
        self.assertIn("disabled", other_page.select_one("button.addtable").attrs)

        inline_write = BeautifulSoup(
            rewrite_legacy_html(
                '<button class="addtable" type="button" onclick="fetch(\'/update\')">Add</button>',
                "/past-projects",
                ORIGIN_HOST,
                VIEWER_URL,
            ),
            "html.parser",
        )
        self.assertIn("disabled", inline_write.button.attrs)

    def test_archived_sheets_reads_are_permitted_by_the_viewer_csp(self):
        script = archived_source("static/js/merge-search-tables.js")
        self.assertIn('$.getJSON("https://sheets.googleapis.com/', script)
        event_templates = (
            "2020-fall-post-event",
            "2021-fall-event",
            "2021-spring-event",
            "2022-fall-event",
            "2022-spring-event",
            "2023-fall-event",
            "2023-spring-event",
            "2024-fall-event",
            "2024-spring-event",
            "2025-fall-event",
            "2025-spring-event",
            "home-post-event",
        )
        for page in event_templates:
            with self.subTest(page=page):
                self.assertIn(
                    'getJSON("https://sheets.googleapis.com/',
                    archived_source(f"templates/home/{page}.html"),
                )
        connect_src = next(directive for directive in _LEGACY_CSP.split("; ") if directive.startswith("connect-src "))
        self.assertEqual(connect_src, "connect-src 'self' https://sheets.googleapis.com")

    def test_rewrites_internal_location_but_preserves_external_location(self):
        self.assertEqual(
            rewrite_location("http://legacy.i2g.ucmerced.edu/admin/", "/about", ORIGIN_HOST, VIEWER_URL),
            f"{VIEWER_URL}/admin/",
        )
        self.assertEqual(
            rewrite_location("https://www.ucmerced.edu/engineering", "/about", ORIGIN_HOST, VIEWER_URL),
            "https://www.ucmerced.edu/engineering",
        )

    def test_rejects_malformed_redirect_location(self):
        with self.assertRaises(InvalidLegacyURL):
            rewrite_location("http://[broken", "/about", ORIGIN_HOST, VIEWER_URL)


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
        with patch("apps.core.legacy_view.rewriting.urljoin", side_effect=ValueError("bad")):
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
