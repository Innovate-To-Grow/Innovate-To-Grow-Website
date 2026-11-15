"""Matching bounce reports to outgoing emails only on reliable identifiers, and saving each bounce once."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce, EmailCategory, OutboundEmail
from apps.core.services.email.bounces.dsn import parse_report
from apps.core.services.email.bounces.matching import match
from apps.core.services.email.bounces.store import save_report
from apps.core.services.email.telemetry import text

from .helpers import make_email
from .ndr_samples import ORIGINAL_ID, exchange_ndr

MatchMethod = EmailBounce.MatchMethod
SUBJECT = "Your login code - Innovate to Grow"


class MatchTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def match(self, **values):
        defaults = {
            "recipient": "nobody@example.com",
            "original_message_id": "",
            "original_subject": SUBJECT,
            "received_at": self.now,
        }
        return match(**{**defaults, **values})

    def test_the_original_message_id_matches_exactly(self):
        email = make_email(internet_message_id=ORIGINAL_ID, recipient="someone@else.org", subject="Other")

        found = self.match(original_message_id=ORIGINAL_ID)

        self.assertEqual((found.email, found.method), (email, MatchMethod.MESSAGE_ID))

    def test_one_json_send_to_the_recipient_with_the_subject_is_an_inferred_match(self):
        email = make_email(recipient="nobody@example.com", subject=SUBJECT, send_format="json")

        found = self.match(original_message_id="<exchange-assigned@prod.outlook.com>")

        self.assertEqual((found.email, found.method), (email, MatchMethod.RECIPIENT))

    def test_the_subject_comparison_ignores_case_and_whitespace(self):
        email = make_email(recipient="nobody@example.com", subject="Your  LOGIN code - Innovate to Grow")

        self.assertEqual(self.match().email, email)

    def test_two_candidates_are_ambiguous_and_stay_unmatched(self):
        make_email(recipient="nobody@example.com", subject=SUBJECT)
        make_email(recipient="nobody@example.com", subject=SUBJECT)

        found = self.match()

        self.assertIsNone(found.email)
        self.assertEqual(found.method, MatchMethod.UNMATCHED)
        self.assertIn("Several", found.note)

    def test_an_email_with_a_known_message_id_is_never_inferred_for_a_report_quoting_another(self):
        # A report about some other message (one staff sent from Outlook, say) to the same person and subject.
        make_email(recipient="nobody@example.com", subject=SUBJECT, internet_message_id="<ours@ucmerced.edu>")

        found = self.match(original_message_id="<someone-elses@prod.outlook.com>")

        self.assertIsNone(found.email)

    def test_emails_outside_the_window_or_never_accepted_do_not_qualify(self):
        make_email(recipient="nobody@example.com", subject=SUBJECT, last_attempt_at=self.now - timedelta(days=30))
        make_email(recipient="nobody@example.com", subject=SUBJECT, status=OutboundEmail.Status.FAILED)
        make_email(recipient="nobody@example.com", subject=SUBJECT, category=EmailCategory.ACCESS_CHECK)

        self.assertIsNone(self.match().email)

    def test_without_a_recipient_or_a_subject_nothing_is_inferred(self):
        make_email(recipient="nobody@example.com", subject=SUBJECT)

        self.assertIsNone(self.match(recipient="").email)
        self.assertIsNone(self.match(original_subject="").email)


class SaveReportTests(TestCase):
    def save(self, raw, graph_id="AAMkAD-1"):
        return save_report(
            mailbox="i2g@ucmerced.edu", graph_id=graph_id, received_at=timezone.now(), report=parse_report(raw)
        )

    def test_a_matched_hard_bounce_confirms_the_failure_but_keeps_the_api_status(self):
        email = make_email(internet_message_id=ORIGINAL_ID, recipient="nobody@example.com", campaign_id=None)

        result = self.save(exchange_ndr())

        (bounce,) = result.created
        self.assertEqual((bounce.classification, bounce.is_permanent, bounce.status_code), ("hard", True, "5.1.10"))
        self.assertEqual(
            (bounce.email, bounce.match_method, bounce.reason), (email, "message_id", "Recipient not found")
        )
        email.refresh_from_db()
        self.assertEqual(email.status, OutboundEmail.Status.ACCEPTED)
        self.assertEqual(email.delivery_status, OutboundEmail.DeliveryStatus.FAILURE_CONFIRMED)
        self.assertEqual(email.bounce_classification, "hard")
        self.assertIsNotNone(email.bounced_at)

    def test_the_same_report_scanned_again_adds_nothing(self):
        make_email(internet_message_id=ORIGINAL_ID)
        self.save(exchange_ndr())

        again = self.save(exchange_ndr())
        moved = self.save(exchange_ndr(), graph_id="AAMkAD-moved")

        self.assertEqual((again.created, again.duplicates), ([], 1))
        self.assertEqual((moved.created, moved.duplicates), ([], 1))
        self.assertEqual(EmailBounce.objects.count(), 1)

    def test_a_campaign_bounce_carries_the_campaign(self):
        email = make_email(internet_message_id=ORIGINAL_ID, campaign_id="0f5e6d7c-1111-4222-8333-444455556666")

        (bounce,) = self.save(exchange_ndr()).created

        self.assertEqual(str(bounce.campaign_id), str(email.campaign_id))

    def test_a_delay_then_a_failure_ends_as_a_confirmed_failure_and_never_softens(self):
        email = make_email(internet_message_id=ORIGINAL_ID)

        self.save(exchange_ndr(status="4.4.7", action="delayed", report_id="<delay@x>"))
        email.refresh_from_db()
        self.assertEqual(email.delivery_status, OutboundEmail.DeliveryStatus.DELAYED)
        self.save(exchange_ndr(status="5.1.10", report_id="<fail@x>"))
        self.save(exchange_ndr(status="5.2.2", report_id="<soft@x>"))
        self.save(exchange_ndr(status="4.4.7", action="delayed", report_id="<late-delay@x>"))

        email.refresh_from_db()
        self.assertEqual(email.delivery_status, OutboundEmail.DeliveryStatus.FAILURE_CONFIRMED)
        self.assertEqual(email.bounce_classification, "hard")

    def test_a_report_about_a_credential_email_keeps_no_original_subject(self):
        # Matched by inference to a JSON send, whose subject was not stored: the report must not store it either.
        make_email(recipient="nobody@example.com", subject="", subject_digest=text.subject_digest(SUBJECT))

        (bounce,) = self.save(exchange_ndr(original_id="<exchange-assigned@prod.outlook.com>")).created

        self.assertEqual((bounce.match_method, bounce.original_subject), (MatchMethod.RECIPIENT, ""))

    def test_token_shaped_text_in_an_unmatched_reports_subject_is_scrubbed(self):
        token = "Zz9" * 22

        (bounce,) = self.save(exchange_ndr(subject=f"Login {token}")).created

        self.assertNotIn(token, bounce.original_subject)

    def test_an_unmatched_report_is_kept_and_says_why(self):
        (bounce,) = self.save(exchange_ndr()).created

        self.assertIsNone(bounce.email)
        self.assertEqual(bounce.match_method, MatchMethod.UNMATCHED)
        self.assertTrue(bounce.match_note)

    def test_a_delivered_notice_records_nothing(self):
        result = self.save(exchange_ndr(status="2.0.0", action="delivered"))

        self.assertEqual((result.created, result.ignored), ([], 1))
