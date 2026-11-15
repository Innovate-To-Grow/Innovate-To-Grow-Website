from pathlib import Path
from zipfile import ZipFile

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from apps.core.legacy_view.content.html_rewriting import rewrite_legacy_html
from apps.core.legacy_view.content.link_rewriting import (
    InvalidLegacyURL,
    rewrite_location,
)
from apps.core.legacy_view.gateway.views import _LEGACY_CSP

VIEWER_URL = "https://d111111abcdef8.cloudfront.net"
ORIGIN_HOST = "172.31.69.63"
ARCHIVE_PATH = Path(__file__).resolve().parents[7] / "archive" / "legacy" / "webpages.zip"


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
