"""Coverage for scam_detector check helpers, structure, and category mapping."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.mail.services.scam_detector import _category_for_reason
from apps.mail.services.scam_detector.checks import (
    check_body,
    displayed_domain,
    extract_links,
    mismatched_link_count,
)
from apps.mail.services.scam_detector.structure import html_has_hidden_content


class CheckBodyTests(SimpleTestCase):
    def test_empty_body_returns_no_findings(self):
        self.assertEqual(check_body({"text": "", "html": ""}), [])

    def test_single_money_amount_low_finding(self):
        findings = check_body({"text": "You won $1,000,000 in our lottery", "html": ""})
        reasons = [reason for _, reason in findings]
        self.assertIn("Body mentions a monetary amount", reasons)


class ExtractLinksTests(SimpleTestCase):
    def test_non_http_links_are_skipped(self):
        html = '<a href="mailto:x@example.com">mail</a><a href="https://example.com">site</a>'
        links = extract_links(html)
        hrefs = [link["href"] for link in links]
        self.assertEqual(hrefs, ["https://example.com"])

    def test_empty_html_returns_empty(self):
        self.assertEqual(extract_links(""), [])

    def test_unparseable_href_domain_is_blank(self):
        html = '<a href="https://example.com/path">x</a>'
        with patch("apps.mail.services.scam_detector.checks.urlparse", side_effect=ValueError("bad url")):
            links = extract_links(html)
        self.assertEqual(links[0]["href_domain"], "")


class DisplayedDomainTests(SimpleTestCase):
    def test_file_extension_lookalike_returns_empty(self):
        # "report.pdf" parses as a domain candidate but is a filename, not a domain.
        self.assertEqual(displayed_domain("Download report.pdf now"), "")

    def test_real_domain_text_returns_domain(self):
        self.assertEqual(displayed_domain("Visit example.com today"), "example.com")

    def test_no_domain_returns_empty(self):
        self.assertEqual(displayed_domain("no domain here"), "")


class MismatchedLinkCountTests(SimpleTestCase):
    def test_counts_mismatched_links(self):
        links = [
            {"href": "https://evil.example", "text": "ucmerced.edu", "href_domain": "evil.example"},
            {"href": "https://ok.example", "text": "ok.example", "href_domain": "ok.example"},
        ]
        self.assertEqual(mismatched_link_count(links), 1)


class HtmlHasHiddenContentTests(SimpleTestCase):
    def test_detects_hidden_content(self):
        self.assertTrue(html_has_hidden_content('<div style="display:none">secret</div>'))

    def test_no_hidden_content_returns_false(self):
        self.assertFalse(html_has_hidden_content("<p>visible</p>"))


class CategoryForReasonTests(SimpleTestCase):
    def test_fallback_category_for_unmatched_reason(self):
        self.assertEqual(_category_for_reason("Something totally unrelated"), "Security signal")

    def test_link_category(self):
        self.assertEqual(_category_for_reason("Contains shortened URL(s)"), "Link integrity")
