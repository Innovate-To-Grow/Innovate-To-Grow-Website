from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from apps.core.legacy_view.rewriting import InvalidLegacyURL, rewrite_legacy_html, rewrite_location

VIEWER_URL = "https://d111111abcdef8.cloudfront.net"
ORIGIN_HOST = "172.31.69.63"


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
