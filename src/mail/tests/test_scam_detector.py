from django.test import SimpleTestCase

from mail.services.scam_detector import (
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    analyze_email,
)


def _msg(**overrides):
    """Build a minimal message dict with sensible defaults."""
    base = {
        "uid": "1",
        "subject": "Hello",
        "from_name": "Alice",
        "from_email": "alice@example.com",
        "to": [{"name": "", "email": "bob@example.com"}],
        "date": "2026-04-10 01:00 PM",
        "html": "",
        "text": "Hi Bob, how are you?",
        "message_id": "<abc@example.com>",
        "references": "",
    }
    base.update(overrides)
    return base


class AnalyzeEmailBasicTest(SimpleTestCase):
    def test_clean_email_returns_low_risk(self):
        result = analyze_email(_msg())
        self.assertEqual(result["risk_level"], "low")
        self.assertLess(result["score"], MEDIUM_THRESHOLD)

    def test_result_keys(self):
        result = analyze_email(_msg())
        self.assertIn("risk_level", result)
        self.assertIn("score", result)
        self.assertIn("reasons", result)
        self.assertIsInstance(result["reasons"], list)


class SenderHeuristicsTest(SimpleTestCase):
    def test_no_display_name_adds_finding(self):
        result = analyze_email(_msg(from_name=""))
        self.assertTrue(any("no display name" in r.lower() for r in result["reasons"]))

    def test_brand_in_name_but_wrong_domain(self):
        result = analyze_email(_msg(from_name="Amazon Support", from_email="support@phishing-site.com"))
        self.assertTrue(any("amazon" in r.lower() and "domain" in r.lower() for r in result["reasons"]))

    def test_brand_freemail(self):
        result = analyze_email(_msg(from_name="PayPal Security", from_email="paypal.security@gmail.com"))
        reasons_lower = " ".join(result["reasons"]).lower()
        self.assertIn("freemail", reasons_lower)

    def test_legitimate_brand_email_no_mismatch(self):
        result = analyze_email(_msg(from_name="Amazon", from_email="noreply@amazon.com"))
        reasons_text = " ".join(result["reasons"]).lower()
        self.assertNotIn("display name mentions", reasons_text)


class SubjectHeuristicsTest(SimpleTestCase):
    def test_urgency_keywords_detected(self):
        result = analyze_email(_msg(subject="URGENT: Verify your account immediately"))
        self.assertTrue(any("urgency" in r.lower() or "scam" in r.lower() for r in result["reasons"]))

    def test_all_caps_subject(self):
        result = analyze_email(_msg(subject="YOU HAVE WON A MILLION DOLLARS"))
        self.assertTrue(any("uppercase" in r.lower() for r in result["reasons"]))

    def test_normal_subject_no_flags(self):
        result = analyze_email(_msg(subject="Meeting tomorrow at 3pm"))
        subject_reasons = [r for r in result["reasons"] if "subject" in r.lower() or "uppercase" in r.lower()]
        self.assertEqual(len(subject_reasons), 0)


class BodyHeuristicsTest(SimpleTestCase):
    def test_urgency_language_in_body(self):
        result = analyze_email(_msg(text="Click here immediately to act now before your account is closed."))
        self.assertTrue(any("urgency" in r.lower() or "pressure" in r.lower() for r in result["reasons"]))

    def test_personal_info_request(self):
        result = analyze_email(_msg(text="Please send us your social security number and bank account details."))
        self.assertTrue(any("personal" in r.lower() or "financial" in r.lower() for r in result["reasons"]))

    def test_generic_greeting(self):
        result = analyze_email(_msg(text="Dear Customer, your account has been locked."))
        self.assertTrue(any("generic greeting" in r.lower() for r in result["reasons"]))

    def test_money_amounts(self):
        result = analyze_email(_msg(text="You are entitled to $5,000,000 and also EUR 2,500,000."))
        self.assertTrue(any("monetary" in r.lower() for r in result["reasons"]))

    def test_clean_body_no_flags(self):
        result = analyze_email(_msg(text="Hi, just checking in about the project."))
        body_reasons = [
            r
            for r in result["reasons"]
            if any(kw in r.lower() for kw in ("urgency", "personal", "greeting", "monetary"))
        ]
        self.assertEqual(len(body_reasons), 0)

    def test_html_fallback_when_no_text(self):
        result = analyze_email(
            _msg(
                text="",
                html="<html><body>Dear Customer, click here to verify your password immediately.</body></html>",
            )
        )
        self.assertTrue(
            any(
                "personal" in r.lower() or "financial" in r.lower() or "pressure" in r.lower()
                for r in result["reasons"]
            )
        )


class LinkHeuristicsTest(SimpleTestCase):
    def test_shortened_url_detected(self):
        result = analyze_email(_msg(html='<a href="https://bit.ly/abc123">Click</a>'))
        self.assertTrue(any("shortened" in r.lower() for r in result["reasons"]))

    def test_ip_based_url_detected(self):
        result = analyze_email(_msg(html='<a href="http://192.168.1.1/login">Login</a>'))
        self.assertTrue(any("ip address" in r.lower() for r in result["reasons"]))

    def test_domain_mismatch_in_link_text(self):
        result = analyze_email(_msg(html='<a href="http://evil-site.com/login">paypal.com</a>'))
        self.assertTrue(any("different domain" in r.lower() for r in result["reasons"]))

    def test_matching_link_text_no_flag(self):
        result = analyze_email(_msg(html='<a href="https://paypal.com/login">paypal.com</a>'))
        link_reasons = [r for r in result["reasons"] if "different domain" in r.lower()]
        self.assertEqual(len(link_reasons), 0)

    def test_many_unique_domains(self):
        links = "".join(f'<a href="https://domain{i}.com">link</a>' for i in range(7))
        result = analyze_email(_msg(html=links))
        self.assertTrue(any("different domains" in r.lower() for r in result["reasons"]))


class StructureHeuristicsTest(SimpleTestCase):
    def test_html_only_no_text_alternative(self):
        result = analyze_email(_msg(text="", html="<html><body>Hello</body></html>"))
        self.assertTrue(any("html-only" in r.lower() or "no plain-text" in r.lower() for r in result["reasons"]))

    def test_hidden_elements_detected(self):
        result = analyze_email(_msg(html='<div style="display:none">hidden tracker</div><p>Hello</p>'))
        self.assertTrue(any("hidden" in r.lower() for r in result["reasons"]))

    def test_zero_font_size_detected(self):
        result = analyze_email(_msg(html='<span style="font-size:0px">invisible</span><p>Hello</p>'))
        self.assertTrue(any("zero-size" in r.lower() for r in result["reasons"]))


class OverallScoringTest(SimpleTestCase):
    def test_medium_risk_threshold(self):
        result = analyze_email(
            _msg(
                from_name="",
                subject="Urgent: Verify your account now",
                text="Dear Customer, click here immediately.",
            )
        )
        self.assertGreaterEqual(result["score"], MEDIUM_THRESHOLD)
        self.assertIn(result["risk_level"], ("medium", "high"))

    def test_high_risk_combined_signals(self):
        result = analyze_email(
            _msg(
                from_name="Amazon Security",
                from_email="security@totally-not-amazon.com",
                subject="URGENT: YOUR ACCOUNT HAS BEEN SUSPENDED",
                text="Dear Customer, your account has been suspended. "
                "Click here immediately to verify your password and social security number. "
                "Failure to respond within 24 hours will result in permanent closure.",
                html='<a href="http://192.168.1.1/phish">amazon.com/verify</a>'
                '<a href="https://bit.ly/fake">Verify Now</a>'
                '<div style="display:none">tracking pixel</div>',
            )
        )
        self.assertGreaterEqual(result["score"], HIGH_THRESHOLD)
        self.assertEqual(result["risk_level"], "high")
        self.assertGreater(len(result["reasons"]), 3)

    def test_legitimate_email_stays_low(self):
        result = analyze_email(
            _msg(
                from_name="John Smith",
                from_email="john.smith@ucmerced.edu",
                subject="Team meeting agenda - April 10",
                text="Hi everyone,\n\nHere is the agenda for our meeting tomorrow.\n\nBest,\nJohn",
            )
        )
        self.assertEqual(result["risk_level"], "low")
        self.assertLess(result["score"], MEDIUM_THRESHOLD)
