import time

from django.test import SimpleTestCase

from apps.core.models import EmailBounce
from apps.core.services.email.bounces import classify as classify_module
from apps.core.services.email.bounces.classify import classify, smtp_code
from apps.core.services.email.bounces.rules import codes, phrases
from apps.core.tests.services.email_monitoring.bounce_reports.test_bounce_categories import Category


class ReplyCodeAndReasonTests(SimpleTestCase):
    def test_the_smtp_reply_code(self):
        for diagnostic, expected in (
            ("550 5.1.1 user unknown", "550"),
            ("550-5.1.1 The email account that you tried to reach does not exist.", "550"),
            ("  421 4.4.1 Connection timed out", "421"),
            ("554: delivery error: dd This user doesn't have a yahoo.com account", "554"),
            ("Remote host said: 550 5.1.1 <x@example.com>: User unknown", "550"),
            ("host mx.example.org said: 452-4.2.2 mailbox full", "452"),
            ("5.1.1 user unknown", ""),
            ("2097654100 is my phone", ""),
            ("Message size: 450 KB", ""),
            ("", ""),
            (None, ""),
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertEqual(smtp_code(diagnostic), expected)

    def test_reasons_prefer_the_codes_own_then_a_phrase_of_the_same_category(self):
        for status, diagnostic, expected in (
            ("5.1.10", "", "Recipient not found"),
            ("5.4.300", "550 5.4.300 Message expired -> Winsock error code: 10060", "Delivery expired"),
            ("4.4.1", "421 4.4.1 Connection timed out", "Connection timed out"),
            ("4.4.1", "421 4.4.1", "Temporary: network or routing problem"),
            (
                "4.7.1",
                "451 4.7.1 Greylisted, try again later",
                "Temporary failure: the server asked to try again later",
            ),
            ("5.0.0", "", "Delivery failed; the report does not say why"),
            (
                "5.5.0",
                "550 5.5.0 Requested action not taken: mailbox unavailable",
                "Delivery failed; the report does not say why",
            ),
            ("5.6.1", "", "Message content problem"),
            (
                "5.7.1",
                "550 5.7.1 Relay access denied",
                "Relay denied: the receiving server would not take our message by this route",
            ),
            ("5.7.607", "", "Rejected as spam, or for our sending reputation or authentication"),
            ("5.1.99", "", "Recipient address problem"),
        ):
            with self.subTest(status=status, diagnostic=diagnostic):
                self.assertEqual(classify("failed", status, diagnostic).reason, expected)

    def test_every_category_has_a_classification_guidance_and_a_hint(self):
        legend = EmailBounce.category_legend()

        self.assertEqual([item["value"] for item in legend], Category.values)
        for category in Category.values:
            with self.subTest(category=category):
                self.assertIn(category, classify_module.COARSE)
                self.assertTrue(EmailBounce.guidance_for(category))
                self.assertTrue(EmailBounce.hint_for(category))
                self.assertEqual(EmailBounce(category=category).category_hint, EmailBounce.hint_for(category))
        self.assertEqual((EmailBounce.guidance_for("bogus"), EmailBounce.hint_for("")), ("", ""))
        self.assertEqual(
            str(EmailBounce(category="relay_denied", recipient="r@example.org")), "Relay denied: r@example.org"
        )
        self.assertEqual(str(EmailBounce(category="", classification="hard")), "Hard bounce: unknown recipient")
        self.assertEqual(str(EmailBounce()), "Bounce report: unknown recipient")
        strong = {category for category, fails in classify_module.ADDRESS_FAILS.items() if fails}
        self.assertEqual(strong, {Category.HARD, Category.MAILBOX_DISABLED})

    def test_the_code_tables(self):
        self.assertEqual(codes.specific(5, 7, 640), Category.SPAM_REJECTED)
        self.assertIsNone(codes.specific(5, 7, 650))
        self.assertEqual(codes.default(5, 1, 6), Category.HARD)
        self.assertEqual(codes.default(5, 1, 5), Category.UNKNOWN)
        self.assertEqual(codes.default(4, 1, 1), Category.TRANSIENT)
        self.assertTrue(codes.is_generic(5, 7, 1))
        self.assertTrue(codes.is_generic(4, 7, 3))
        self.assertFalse(codes.is_generic(4, 7, 26))
        self.assertFalse(codes.is_generic(5, 7, 9))
        self.assertEqual(codes.reason("bad"), "")
        self.assertIsNone(phrases.refine("nothing to see here", phrases.ALL))


class HostileInputTests(SimpleTestCase):
    def test_long_repetitive_diagnostics_stay_fast(self):
        seeds = ("account ", "relay ", "a", "max ", "sender address ", "dns ", "mailbox ", "0 ", "doesn't have a ")
        started = time.perf_counter()
        for seed in seeds:
            diagnostic = (seed * (5000 // len(seed)))[:5000]
            for status in ("", "5.0.0", "5.7.1", "4.7.1", "5.4.4", "5.2.3"):
                classify("failed", status, diagnostic)
        self.assertLess(time.perf_counter() - started, 2.0)
