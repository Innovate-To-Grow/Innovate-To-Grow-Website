"""Coverage for scam_detector check helpers, structure, and category mapping."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.mail.services.scam_detector import _category_for_reason
from apps.mail.services.scam_detector.checks import (
    check_address_alignment,
    check_authentication,
    check_body,
    check_links,
    check_sender,
    displayed_domain,
    extract_links,
    extract_text_urls,
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

    def test_authentication_category(self):
        self.assertEqual(_category_for_reason("Email failed DMARC authentication"), "Sender authentication")

    def test_sender_lookalike_category(self):
        self.assertEqual(_category_for_reason('Domain "x" imitates "amazon"'), "Sender identity")


class CheckAuthenticationTests(SimpleTestCase):
    def test_no_header_returns_no_findings(self):
        self.assertEqual(check_authentication({"authentication_results": ""}), [])

    def test_dmarc_fail_scored_highest(self):
        findings = check_authentication({"authentication_results": "mx.google.com; dmarc=fail; spf=pass"})
        self.assertEqual(findings[0][0], 3)
        self.assertIn("DMARC", findings[0][1])

    def test_spf_fail_and_dkim_fail(self):
        findings = check_authentication({"authentication_results": "spf=fail dkim=fail dmarc=pass"})
        reasons = " ".join(reason for _, reason in findings)
        self.assertIn("SPF", reasons)
        self.assertIn("DKIM", reasons)

    def test_spf_softfail_low_score(self):
        findings = check_authentication({"authentication_results": "spf=softfail"})
        self.assertEqual(findings, [(1, "Email soft-failed SPF authentication")])

    def test_all_pass_returns_no_findings(self):
        self.assertEqual(check_authentication({"authentication_results": "spf=pass dkim=pass dmarc=pass"}), [])


class CheckAddressAlignmentTests(SimpleTestCase):
    def test_no_from_domain_returns_empty(self):
        self.assertEqual(check_address_alignment({"from_email": ""}), [])

    def test_reply_to_mismatch_flagged(self):
        findings = check_address_alignment({"from_email": "support@amazon.com", "reply_to": "attacker@evil.com"})
        self.assertEqual(findings[0][0], 2)
        self.assertIn("Reply-To", findings[0][1])

    def test_return_path_mismatch_flagged(self):
        findings = check_address_alignment({"from_email": "support@amazon.com", "return_path": "bounce@evil.com"})
        self.assertIn("Return-Path", findings[0][1])

    def test_aligned_subdomain_not_flagged(self):
        findings = check_address_alignment({"from_email": "noreply@mail.amazon.com", "reply_to": "support@amazon.com"})
        self.assertEqual(findings, [])


class CheckSenderDomainIntelTests(SimpleTestCase):
    def test_punycode_sender_domain_flagged(self):
        findings = check_sender({"from_name": "Service", "from_email": "x@xn--80ak6aa92e.com"})
        self.assertTrue(any("punycode" in reason.lower() for _, reason in findings))

    def test_lookalike_sender_domain_flagged(self):
        findings = check_sender({"from_name": "Billing", "from_email": "x@amaz0n.com"})
        self.assertTrue(any("imitates" in reason.lower() or "resembles" in reason.lower() for _, reason in findings))


class ExtractTextUrlsTests(SimpleTestCase):
    def test_extracts_and_strips_trailing_punctuation(self):
        links = extract_text_urls("See https://bit.ly/abc, then reply.")
        self.assertEqual(links[0]["href"], "https://bit.ly/abc")
        self.assertEqual(links[0]["href_domain"], "bit.ly")

    def test_empty_text_returns_empty(self):
        self.assertEqual(extract_text_urls(""), [])

    def test_unparseable_url_domain_blank(self):
        with patch("apps.mail.services.scam_detector.checks.urlparse", side_effect=ValueError("bad")):
            links = extract_text_urls("visit https://example.com now")
        self.assertEqual(links[0]["href_domain"], "")


class CheckLinksRawTextTests(SimpleTestCase):
    def test_raw_text_shortener_detected(self):
        findings = check_links({"html": "", "text": "Click https://bit.ly/abc to verify"})
        self.assertTrue(any("shortened" in reason.lower() for _, reason in findings))

    def test_punycode_link_domain_flagged(self):
        findings = check_links({"html": '<a href="https://xn--80ak6aa92e.com/login">login</a>', "text": ""})
        self.assertTrue(any("punycode" in reason.lower() for _, reason in findings))

    def test_single_link_brand_lookalike_flagged(self):
        findings = check_links({"html": '<a href="https://amaz0n.com/login">login</a>', "text": ""})
        self.assertTrue(any("imitates" in reason.lower() for _, reason in findings))

    def test_multiple_link_brand_lookalikes_flagged(self):
        html = '<a href="https://amaz0n.com/a">a</a><a href="https://paypai.com/b">b</a>'
        findings = check_links({"html": html, "text": ""})
        self.assertTrue(any("impersonate known brands" in reason.lower() for _, reason in findings))

    def test_anchor_and_text_url_deduped(self):
        msg = {"html": '<a href="https://bit.ly/x">go</a>', "text": "also https://bit.ly/x here"}
        findings = check_links(msg)
        self.assertTrue(any("1 shortened" in reason.lower() for _, reason in findings))
