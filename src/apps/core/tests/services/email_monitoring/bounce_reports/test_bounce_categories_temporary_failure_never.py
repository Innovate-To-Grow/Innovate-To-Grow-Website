from django.test import SimpleTestCase

from apps.core.services.email.bounces.classify import classify, effective_status
from apps.core.tests.services.email_monitoring.bounce_reports.test_bounce_categories import (
    GMAIL_RECEIVING_RATE,
    Category,
    Classification,
    category_of,
)


class CodePrecedenceTests(SimpleTestCase):
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
            ("5.4.1", Category.UNKNOWN),
            ("5.4.4", Category.UNKNOWN),
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

    def test_ambiguous_route_codes_can_be_recipient_temporary_or_sender_failures(self):
        self.assertEqual(category_of("5.4.1", "550 5.4.1 Recipient address rejected: Access denied"), Category.HARD)
        self.assertEqual(category_of("5.4.1", "550 5.4.1 No answer from host: connection timed out"), "transient")
        host_retry = "Host or domain name not found. Name service error for name=x type=MX: Host not found, try again"
        self.assertEqual(category_of("5.4.4", host_retry), Category.TRANSIENT)
        self.assertEqual(category_of("5.4.4", "550 5.4.4 relay access denied (spam)"), Category.RELAY_DENIED)

        self.assertEqual(category_of("5.4.1", "550 5.4.1 SPF validation failed"), Category.SPAM_REJECTED)
        self.assertEqual(category_of("5.4.1", "550 5.4.1 No answer from host"), Category.TRANSIENT)
        self.assertEqual(category_of("5.4.4", "550 5.4.4 Unable to route"), Category.UNKNOWN)
        self.assertEqual(category_of("5.4.4", "550 5.4.4 recipient domain does not exist"), Category.HARD)

    def test_gmail_receiving_rate_limit_is_temporary_not_a_disabled_mailbox(self):
        # Gmail returns 5.2.1 both for a disabled account and for a recipient receiving mail too fast (a limit that
        # typically lifts within a day): only the second's text makes it temporary.
        verdict = classify("failed", "5.2.1", GMAIL_RECEIVING_RATE)

        self.assertEqual(
            (verdict.category, verdict.classification, verdict.is_permanent, verdict.smtp_code),
            (Category.TRANSIENT, Classification.SOFT, False, "550"),
        )
        self.assertEqual(verdict.reason, "The recipient is receiving mail too fast: a temporary limit")
        wrapped = f"550 5.0.350 Remote server returned an error -> {GMAIL_RECEIVING_RATE}"
        self.assertEqual(category_of("5.0.350", wrapped), Category.TRANSIENT)
        self.assertEqual(category_of("5.2.1", "550 5.2.1 Mailbox temporarily disabled"), Category.TRANSIENT)
        for diagnostic in (
            "550-5.2.1 The email account that you tried to reach is disabled.",
            "",
        ):
            with self.subTest(diagnostic=diagnostic):
                verdict = classify("failed", "5.2.1", diagnostic)
                self.assertEqual((verdict.category, verdict.is_permanent), (Category.MAILBOX_DISABLED, True))
                self.assertEqual(verdict.reason, "Recipient mailbox is disabled")

    def test_contradictory_address_and_sender_reasons_on_an_ambiguous_code_need_review(self):
        verdict = classify("failed", "5.2.1", "550 5.2.1 user unknown, relay access denied (spam)")
        self.assertEqual((verdict.category, verdict.is_permanent), (Category.UNKNOWN, None))

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
