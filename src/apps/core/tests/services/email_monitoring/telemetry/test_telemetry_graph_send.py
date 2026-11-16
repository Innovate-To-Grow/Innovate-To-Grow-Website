"""Email telemetry of sends through the delivery facade and the real Microsoft Graph provider.

Only ``transport.post`` is replaced (``FakeGraph``), so every request the provider would make is classified by the
real code: the token step, sendMail, its HTTP answer, Microsoft's error codes and ids, and network failures.
"""

import json

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import EmailCategory, OutboundEmail, OutboundEmailAttempt
from apps.core.services.delivery_rates.families import clear_gate_cache
from apps.core.services.email import (
    EmailDeliveryError,
    EmailMessage,
    PermanentEmailDeliveryError,
)

from ..helpers import REQUEST_ID, SENDER, GraphSendingMixin, accepted, graph_error

Status = OutboundEmail.Status
Outcome = OutboundEmailAttempt.Outcome


def stored_text() -> str:
    """Every value the telemetry tables hold, as one string, for leak scans."""
    rows = [*OutboundEmail.objects.values(), *OutboundEmailAttempt.objects.values()]
    return json.dumps(rows, default=str)


class TelemetryTestCase(GraphSendingMixin, TestCase):
    def setUp(self):
        cache.clear()
        super().setUp()
        self.addCleanup(clear_gate_cache)

    def only_email(self) -> OutboundEmail:
        self.assertEqual(OutboundEmail.objects.count(), 1)
        return OutboundEmail.objects.get()

    def send_failing(self, answer, error_class=EmailDeliveryError):
        self.fake.script(send=answer)
        with self.assertRaises(error_class):
            self.send()
        email = self.only_email()
        return email, email.attempts.get()


class AcceptedSendTests(TelemetryTestCase):
    def test_an_accepted_send_is_api_accepted_and_its_delivery_stays_unknown(self):
        self.fake.script(send=accepted())

        self.send()

        email = self.only_email()
        self.assertEqual(email.status, Status.ACCEPTED)
        self.assertEqual(email.delivery_status, OutboundEmail.DeliveryStatus.UNKNOWN)
        self.assertNotIn("deliver", email.get_status_display().lower())
        self.assertEqual((email.provider, email.mailbox, email.recipient), ("graph", SENDER, "person@example.com"))
        self.assertEqual((email.recipient_count, email.attempt_count, email.category), (1, 1, EmailCategory.OTHER))
        self.assertIsNotNone(email.accepted_at)
        attempt = email.attempts.get()
        self.assertEqual(
            (attempt.outcome, attempt.http_status, attempt.operation), (Outcome.ACCEPTED, 202, "send_mail")
        )
        self.assertEqual(attempt.endpoint, "POST /v1.0/users/{mailbox}/sendMail")
        self.assertEqual(attempt.request_id, REQUEST_ID)
        self.assertTrue(attempt.token_fresh)
        self.assertIsNotNone(attempt.duration_ms)
        self.assertIsNotNone(attempt.response_ms)

    def test_the_send_carries_a_client_request_id_and_the_attempt_keeps_it(self):
        self.fake.script(send=accepted())

        self.send()

        sent_id = self.fake.send_requests[0].headers["client-request-id"]
        self.assertEqual(OutboundEmailAttempt.objects.get().client_request_id, sent_id)

    def test_a_mime_send_keeps_its_message_id_and_a_json_send_has_none(self):
        self.fake.script(send=accepted())

        self.send(EmailMessage(subject="Mime", to=("a@example.com",), html_body="<p>x</p>"))
        self.send(EmailMessage(subject="Code", to=("b@example.com",), html_body="<p>x</p>", keep_sent_copy=False))

        mime = OutboundEmail.objects.get(recipient="a@example.com")
        json_send = OutboundEmail.objects.get(recipient="b@example.com")
        self.assertEqual(mime.send_format, "mime")
        self.assertRegex(mime.internet_message_id, r"^<.+@ucmerced\.edu>$")
        self.assertEqual((json_send.send_format, json_send.internet_message_id), ("json", ""))

    def test_a_credential_emails_subject_is_never_stored_only_its_digest(self):
        self.fake.script(send=accepted())
        link = "https://i2g.example.edu/login-link#token=" + "a1B2c3D4" * 8

        self.send(
            EmailMessage(subject=f"Sign in: {link}", to=("m@example.com",), html_body="<p>x</p>", keep_sent_copy=False)
        )
        self.send(EmailMessage(subject=f"News {link}", to=("n@example.com",), html_body="<p>x</p>"))

        credential = OutboundEmail.objects.get(recipient="m@example.com")
        self.assertEqual(credential.subject, "")
        self.assertEqual(len(credential.subject_digest), 64)
        other = OutboundEmail.objects.get(recipient="n@example.com")
        self.assertNotIn("a1B2c3D4" * 8, other.subject)
        self.assertIn("[redacted]", other.subject)
        self.assertNotIn("a1B2c3D4" * 8, stored_text())

    def test_the_tracking_context_names_category_campaign_and_source(self):
        self.fake.script(send=accepted())
        campaign_id = "1e0b7c1c-1111-4222-8333-444455556666"

        self.send(category="campaign", campaign_id=campaign_id, source_type="mail.recipientlog", source_id="log-1")

        email = self.only_email()
        self.assertEqual(email.category, EmailCategory.CAMPAIGN)
        self.assertEqual(str(email.campaign_id), campaign_id)
        self.assertEqual((email.source_type, email.source_id), ("mail.recipientlog", "log-1"))

    def test_an_unknown_category_is_filed_under_other_and_every_recipient_is_counted(self):
        self.fake.script(send=accepted())
        message = EmailMessage(
            subject="Hi", to=("One <one@example.com>",), cc=("TWO@example.com",), html_body="<p>x</p>"
        )

        self.send(message, category="no-such-category")

        email = self.only_email()
        self.assertEqual(email.category, EmailCategory.OTHER)
        self.assertEqual(email.recipients, ["one@example.com", "two@example.com"])
        self.assertEqual((email.recipient, email.recipient_count), ("one@example.com", 2))


class FailedSendTests(TelemetryTestCase):
    def test_a_bad_request_is_a_permanent_api_failure_with_its_graph_error_code(self):
        email, attempt = self.send_failing(graph_error(400, "ErrorInvalidRecipients"), PermanentEmailDeliveryError)

        self.assertEqual((email.status, email.delivery_status), (Status.FAILED, "not_applicable"))
        self.assertEqual(
            (attempt.outcome, attempt.http_status, attempt.error_kind), (Outcome.PERMANENT, 400, "bad_request")
        )
        self.assertEqual(
            (attempt.error_code, email.last_error_code), ("ErrorInvalidRecipients", "ErrorInvalidRecipients")
        )
        self.assertEqual(attempt.request_id, REQUEST_ID)
        self.assertIn("ErrorInvalidRecipients", email.last_error)
