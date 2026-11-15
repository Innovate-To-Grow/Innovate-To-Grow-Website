"""Bounce categories (``bounces.classify`` and ``bounces.rules``): the SMTP reply code and the enhanced status code
decide, the diagnostic text only refines a generic code, and only a missing address or a disabled mailbox is evidence
against the address."""

from django.test import SimpleTestCase

from apps.core.models import EmailBounce
from apps.core.services.email.bounces.classify import classify
from apps.core.services.email.bounces.recording.dsn import parse_report

from ..review_cases import CASES, CASES_BY_NAME

Category = EmailBounce.Category
Classification = EmailBounce.Classification
GMAIL_RECEIVING_RATE = (
    "550-5.2.1 The user you are trying to contact is receiving mail at a rate that prevents additional messages from "
    "being delivered. For more information, go to https://support.google.com/mail/?p=ReceivingRatePerm - gsmtp"
)


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
            ("5.1.10", "550 5.1.10 RecipientNotFound; try again later", Category.HARD),
            ("4.2.2", "452 4.2.2 user unknown", Category.MAILBOX_FULL),
        ):
            with self.subTest(status=status):
                self.assertEqual(category_of(status, diagnostic), expected)
