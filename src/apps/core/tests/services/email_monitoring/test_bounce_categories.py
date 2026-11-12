"""Bounce categories (``bounces.classify`` and ``bounces.rules``): the SMTP reply code and the enhanced status code
decide, the diagnostic text only refines a generic code, and only a missing address or a disabled mailbox is evidence
against the address."""

import time

from django.test import SimpleTestCase

from apps.core.models import EmailBounce
from apps.core.services.email.bounces import classify as classify_module
from apps.core.services.email.bounces.classify import classify, effective_status, smtp_code
from apps.core.services.email.bounces.dsn import parse_report
from apps.core.services.email.bounces.rules import codes, phrases

from .review_cases import CASES, CASES_BY_NAME

Category = EmailBounce.Category
Classification = EmailBounce.Classification


def category_of(status: str, diagnostic: str = "", action: str = "failed") -> str:
    return classify(action, status, diagnostic).category


def verdict_of(case_name: str):
    (row,) = parse_report(CASES_BY_NAME[case_name].raw).recipients
    return classify(row.action, row.status, row.diagnostic)


class ReviewCaseTests(SimpleTestCase):
    """The cases the first review of real bounces raised, read through the parser (synthetic reports)."""

    def test_each_case_gets_its_category_classification_and_reply_code(self):
        for case in CASES:
            with self.subTest(case=case.name):
                (row,) = parse_report(case.raw).recipients
                verdict = classify(row.action, row.status, row.diagnostic)
                self.assertEqual(row.recipient, case.recipient)
                self.assertEqual(
                    (verdict.category, verdict.classification, verdict.is_permanent, verdict.smtp_code),
                    (
                        case.expected.category,
                        case.expected.classification,
                        case.expected.is_permanent,
                        case.expected.smtp_code,
                    ),
                )

    def test_connection_timeouts_are_temporary_and_never_evidence_against_the_address(self):
        for name in ("gmail_connection_timeout", "business_connection_timeout", "connection_refused_expired"):
            with self.subTest(case=name):
                verdict = verdict_of(name)
                self.assertEqual((verdict.category, verdict.is_permanent), (Category.TRANSIENT, False))
                self.assertNotEqual(verdict.classification, Classification.HARD)

    def test_a_timeout_names_its_cause_when_the_code_does_not(self):
        self.assertEqual(verdict_of("business_connection_timeout").reason, "Connection timed out")
        self.assertEqual(verdict_of("gmail_connection_timeout").reason, "Delivery expired")

    def test_relay_and_spam_rejections_point_at_our_sending_not_the_contact(self):
        relay, spam = verdict_of("relay_denied"), verdict_of("proofpoint_spam")

        self.assertEqual((relay.category, spam.category), (Category.RELAY_DENIED, Category.SPAM_REJECTED))
        relay_guidance = EmailBounce.guidance_for(relay.category)
        spam_guidance = EmailBounce.guidance_for(spam.category)
        self.assertIn("Our sending side", relay_guidance)
        self.assertIn("route and authorisation", relay_guidance)
        self.assertIn("Our sending side", spam_guidance)
        self.assertIn("reputation", spam_guidance)
        for guidance in (relay_guidance, spam_guidance):
            self.assertIn("not the contact", guidance)

    def test_a_zero_kb_size_limit_is_a_disabled_mailbox_and_a_real_limit_a_message_problem(self):
        verdict = verdict_of("zero_kb_size_limit")

        self.assertEqual((verdict.category, verdict.is_permanent), (Category.MAILBOX_DISABLED, True))
        self.assertIn("0 KB", verdict.reason)
        too_large = "550 5.2.3 RESOLVER.RST.RecipSizeLimit; message too large; Max size allowed: 10240 KB"
        self.assertEqual(category_of("5.2.3", too_large), Category.TRANSIENT)
        self.assertEqual(
            category_of("5.3.4", "552 5.3.4 Message size exceeds maximum size limit of 0 KB"), "mailbox_disabled"
        )
        self.assertEqual(
            category_of("5.0.0", "552 message size exceeds the limit of 0 bytes"), Category.MAILBOX_DISABLED
        )
        self.assertEqual(category_of("5.0.0", "552 message size exceeds the limit of 0.5 MB"), Category.TRANSIENT)

    def test_yahoo_without_a_reason_is_unknown_and_yahoo_policy_reasons_a_spam_rejection(self):
        generic, policy = verdict_of("yahoo_generic_554"), verdict_of("yahoo_policy_reasons")

        self.assertEqual((generic.category, generic.is_permanent), (Category.UNKNOWN, None))
        self.assertEqual(policy.category, Category.SPAM_REJECTED)
        yahoo_missing = "554 delivery error: dd This user doesn't have a yahoo.com account (x@yahoo.example) [0]"
        yahoo_disabled = (
            "554 delivery error: dd Sorry your message cannot be delivered. This mailbox is disabled (554.30)"
        )
        self.assertEqual(category_of("", yahoo_missing), Category.HARD)
        self.assertEqual(category_of("", yahoo_disabled), Category.MAILBOX_DISABLED)
        self.assertEqual(
            category_of("", "554 Message not allowed - [PH01] Email not accepted for policy reasons"), "spam_rejected"
        )

    def test_an_address_that_does_not_exist_is_strong_evidence(self):
        verdict = verdict_of("address_not_found")

        self.assertEqual((verdict.category, verdict.is_permanent), (Category.HARD, True))


class CodePrecedenceTests(SimpleTestCase):
    def test_specific_codes_win_over_any_text(self):
        for status, diagnostic, expected in (
            ("5.1.1", "550 5.1.1 user unknown (anti-spam gateway, connection timed out)", Category.HARD),
            ("5.4.300", "550 5.4.300 Message expired: user unknown", Category.TRANSIENT),
            ("5.7.54", "550 5.7.54 user unknown", Category.RELAY_DENIED),
            ("5.2.2", "552 5.2.2 relay access denied", Category.MAILBOX_FULL),
            ("5.2.1", "550 5.2.1 try again later", Category.MAILBOX_DISABLED),
            ("4.2.2", "452 4.2.2 user unknown", Category.MAILBOX_FULL),
        ):
            with self.subTest(status=status):
                self.assertEqual(category_of(status, diagnostic), expected)

    def test_a_temporary_failure_is_never_a_missing_address_or_a_disabled_mailbox(self):
        for status, diagnostic, expected in (
            ("4.0.0", "450 4.0.0 user unknown", Category.TRANSIENT),
            ("4.2.0", "450 4.2.0 This mailbox is disabled", Category.TRANSIENT),
            ("4.7.1", "450 4.7.1 Recipient address rejected: user unknown", Category.TRANSIENT),
            ("4.4.1", "421 4.4.1 Connection timed out", Category.TRANSIENT),
            ("", "450 Requested action not taken: mailbox unavailable", Category.TRANSIENT),
            ("", "450 user unknown, try again", Category.TRANSIENT),
            ("4.2.0", "452 4.2.0 Mailbox full", Category.MAILBOX_FULL),
            ("4.7.1", "454 4.7.1 <x@example.com>: Relay access denied", Category.RELAY_DENIED),
            ("4.7.0", "421 4.7.0 [TSS04] Messages temporarily deferred due to user complaints", Category.SPAM_REJECTED),
            ("4.7.28", "421 4.7.28 Unusual rate of unsolicited mail from your IP", Category.SPAM_REJECTED),
            ("4.7.1", "451 4.7.1 Greylisting in action, please come back later", Category.TRANSIENT),
        ):
            with self.subTest(status=status, diagnostic=diagnostic):
                verdict = classify("failed", status, diagnostic)
                self.assertEqual(verdict.category, expected)
                self.assertFalse(verdict.is_permanent)

    def test_generic_permanent_codes_are_refined_by_their_text_or_keep_their_default(self):
        for status, diagnostic, expected in (
            ("5.0.0", "", Category.UNKNOWN),
            ("5.0.0", "550 5.0.0 <x@example.com>... User unknown", Category.HARD),
            ("5.0.0", "550 5.0.0 The account you tried to reach is disabled", Category.MAILBOX_DISABLED),
            ("5.0.0", "552 5.0.0 Mailbox is full", Category.MAILBOX_FULL),
            ("5.0.0", "550 5.0.0 Message rejected as spam", Category.SPAM_REJECTED),
            ("5.0.0", "550 5.0.0 relaying denied", Category.RELAY_DENIED),
            ("5.0.0", "550 5.0.0 not authorized to send to this recipient", Category.POLICY_REJECTED),
            ("5.0.0", "550 5.0.0 Your account has been disabled for sending spam", Category.SPAM_REJECTED),
            ("5.1.0", "550 5.1.0 Sender denied", Category.POLICY_REJECTED),
            ("5.1.0", "550 5.1.0 Address rejected", Category.HARD),
            ("5.2.0", "", Category.UNKNOWN),
            ("5.3.0", "", Category.TRANSIENT),
            ("5.4.0", "550 5.4.0 nonexistent domain", Category.HARD),
            ("5.4.0", "", Category.TRANSIENT),
            ("5.5.0", "550 5.5.0 Requested action not taken: mailbox unavailable", Category.UNKNOWN),
            ("5.5.1", "550 5.5.1 no such user", Category.HARD),
            ("5.6.0", "", Category.TRANSIENT),
            ("5.7.0", "", Category.POLICY_REJECTED),
            ("5.7.1", "550 5.7.1 Service unavailable; client host blocked using zen.spamhaus.example", "spam_rejected"),
            ("5.7.1", "550 5.7.1 Recipient address rejected: User unknown", Category.HARD),
            ("5.7.1", "550 5.7.1 Unable to deliver: connection timed out", Category.POLICY_REJECTED),
            ("5.7.1", "550 5.7.1 Sender address rejected: Domain not found", Category.SPAM_REJECTED),
            ("5.7.1", "550 5.7.1 RESOLVER.RST.AuthRequired; authentication required", Category.POLICY_REJECTED),
        ):
            with self.subTest(status=status, diagnostic=diagnostic):
                self.assertEqual(category_of(status, diagnostic), expected)

    def test_unrecognised_permanent_codes_are_unknown_not_hard(self):
        for status in ("5.1.99", "5.2.9", "5.9.9", "5.8.1"):
            with self.subTest(status=status):
                verdict = classify("failed", status)
                self.assertEqual((verdict.category, verdict.is_permanent), (Category.UNKNOWN, None))

    def test_exchange_online_codes(self):
        for status, expected in (
            ("5.1.10", Category.HARD),
            ("5.4.1", Category.HARD),
            ("5.4.4", Category.HARD),
            ("5.4.310", Category.HARD),
            ("5.2.1", Category.MAILBOX_DISABLED),
            ("5.4.312", Category.TRANSIENT),
            ("5.4.316", Category.TRANSIENT),
            ("5.4.14", Category.TRANSIENT),
            ("5.4.7", Category.TRANSIENT),
            ("5.2.121", Category.TRANSIENT),
            ("5.1.90", Category.TRANSIENT),
            ("5.1.7", Category.SPAM_REJECTED),
            ("5.1.8", Category.SPAM_REJECTED),
            ("5.7.9", Category.SPAM_REJECTED),
            ("5.7.23", Category.SPAM_REJECTED),
            ("5.7.26", Category.SPAM_REJECTED),
            ("5.7.350", Category.SPAM_REJECTED),
            ("5.7.501", Category.SPAM_REJECTED),
            ("5.7.509", Category.SPAM_REJECTED),
            ("5.7.513", Category.SPAM_REJECTED),
            ("5.7.606", Category.SPAM_REJECTED),
            ("5.7.649", Category.SPAM_REJECTED),
            ("5.7.708", Category.SPAM_REJECTED),
            ("5.7.750", Category.SPAM_REJECTED),
            ("5.7.54", Category.RELAY_DENIED),
            ("5.7.57", Category.RELAY_DENIED),
            ("5.7.60", Category.RELAY_DENIED),
            ("5.7.64", Category.RELAY_DENIED),
            ("5.7.12", Category.POLICY_REJECTED),
            ("5.7.124", Category.POLICY_REJECTED),
            ("5.7.133", Category.POLICY_REJECTED),
            ("5.7.650", Category.POLICY_REJECTED),
        ):
            with self.subTest(status=status):
                self.assertEqual(category_of(status), expected)

    def test_the_ambiguous_codes_only_become_temporary(self):
        self.assertEqual(category_of("5.4.1", "550 5.4.1 Recipient address rejected: Access denied"), Category.HARD)
        self.assertEqual(category_of("5.4.1", "550 5.4.1 No answer from host: connection timed out"), "transient")
        host_retry = "Host or domain name not found. Name service error for name=x type=MX: Host not found, try again"
        self.assertEqual(category_of("5.4.4", host_retry), Category.TRANSIENT)
        self.assertEqual(category_of("5.4.4", "550 5.4.4 relay access denied (spam)"), Category.HARD)

    def test_reports_without_a_code(self):
        for diagnostic, expected in (
            ("550 User unknown", Category.HARD),
            ("550 Host not found", Category.HARD),
            ("421 Service not available, try again later", Category.TRANSIENT),
            ("452 Mailbox full", Category.MAILBOX_FULL),
            ("421 Messages from 192.0.2.1 temporarily deferred [TSS04]", Category.SPAM_REJECTED),
            ("550 Requested action not taken: mailbox unavailable", Category.UNKNOWN),
            ("connection timed out while talking to mx.example.org", Category.TRANSIENT),
            ("550 something nobody recognises", Category.UNKNOWN),
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertEqual(category_of("", diagnostic), expected)
        verdict = classify("failed", "", "")
        self.assertEqual((verdict.category, verdict.reason), (Category.UNKNOWN, "The report gives no status code"))

    def test_a_generic_status_uses_the_specific_code_its_diagnostic_quotes(self):
        quoted = "Remote host said: 550 5.1.1 <x@example.com>: Recipient address rejected"
        self.assertEqual(effective_status("5.0.0", quoted), "5.1.1")
        self.assertEqual(effective_status("5.0.0", "550 4.4.7 QUEUE.Expired; message expired"), "5.0.0")
        self.assertEqual(effective_status("5.1.1", "554 5.7.1 rejected"), "5.1.1")
        self.assertEqual(effective_status("", "no code at all"), "")
        self.assertEqual(effective_status("5.0.0", "550 5.0.0 then 5.7.1 then 5.5.0"), "5.0.0")
        self.assertEqual(category_of("5.0.0", quoted), Category.HARD)
        self.assertEqual(category_of("4.0.0", "450 4.0.0 then 4.2.2 Mailbox full"), Category.MAILBOX_FULL)

    def test_delays_are_never_failures(self):
        verdict = classify("delayed", "4.4.1", "421 4.4.1 Connection timed out")

        self.assertEqual(
            (verdict.category, verdict.classification, verdict.is_permanent, verdict.smtp_code),
            (Category.DELAYED, Classification.DELAYED, False, "421"),
        )
        self.assertEqual(classify("Delayed", "").reason, "Delivery delayed; the server keeps retrying")

    def test_reports_that_the_message_went_through_are_ignored(self):
        for action, status in (("delivered", "2.0.0"), ("relayed", ""), ("expanded", "2.1.5"), ("", "2.0.0")):
            with self.subTest(action=action, status=status):
                self.assertIsNone(classify(action, status, "250 OK"))


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
