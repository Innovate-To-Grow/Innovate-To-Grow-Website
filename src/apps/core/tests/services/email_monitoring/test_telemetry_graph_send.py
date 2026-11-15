"""Email telemetry of sends through the delivery facade and the real Microsoft Graph provider.

Only ``transport.post`` is replaced (``FakeGraph``), so every request the provider would make is classified by the
real code: the token step, sendMail, its HTTP answer, Microsoft's error codes and ids, and network failures.
"""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailCategory, OutboundEmail, OutboundEmailAttempt
from apps.core.services.background_jobs import JobClaimLost
from apps.core.services.delivery_rates import RateDeferred, RateRefused
from apps.core.services.delivery_rates.families import clear_gate_cache
from apps.core.services.email import (
    EmailDeliveryError,
    EmailMessage,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
    deliver_email,
)
from apps.core.services.email.exceptions import EmailRateDeferred
from apps.core.services.email.graph import transport
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.services.email.telemetry import job_tracking
from apps.core.tests.services.test_email_graph import ACCESS_TOKEN, KEY_LINE

from .helpers import BODY_TEXT, REQUEST_ID, SENDER, GraphSendingMixin, accepted, graph_error, monitoring_settings

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

    def test_a_throttle_records_429_and_the_retry_after_microsoft_asked_for(self):
        email, attempt = self.send_failing(
            graph_error(429, "ApplicationThrottled", headers={"retry-after": "17"}), TransientEmailDeliveryError
        )

        self.assertEqual((attempt.http_status, attempt.error_kind, attempt.retry_after_seconds), (429, "throttled", 17))
        self.assertEqual(
            (attempt.outcome, email.status, email.last_error_kind), (Outcome.TRANSIENT, Status.FAILED, "throttled")
        )

    def test_an_unauthorized_send_is_an_authentication_failure(self):
        email, attempt = self.send_failing(graph_error(401, "InvalidAuthenticationToken"), TransientEmailDeliveryError)

        self.assertEqual((attempt.http_status, attempt.error_kind, email.status), (401, "auth", Status.FAILED))

    def test_a_mailbox_restriction_is_classified_as_such(self):
        email, attempt = self.send_failing(graph_error(403, "ErrorAccessDenied"), PermanentEmailDeliveryError)

        self.assertEqual((attempt.http_status, attempt.error_kind), (403, "mailbox_restricted"))

    def test_another_forbidden_answer_is_access_denied(self):
        _email, attempt = self.send_failing(graph_error(403, "Forbidden"))

        self.assertEqual(attempt.error_kind, "forbidden")

    def test_not_found_is_classified(self):
        _email, attempt = self.send_failing(graph_error(404, "ResourceNotFound"))

        self.assertEqual((attempt.http_status, attempt.error_kind), (404, "not_found"))

    def test_a_server_error_may_have_sent_the_email_so_its_outcome_is_unknown(self):
        email, attempt = self.send_failing(graph_error(500, "InternalServerError"), UncertainEmailDeliveryError)

        self.assertEqual(
            (attempt.outcome, attempt.error_kind, email.status), (Outcome.UNCERTAIN, "server_error", Status.UNCERTAIN)
        )

    def test_service_unavailable_is_retryable_and_keeps_retry_after(self):
        email, attempt = self.send_failing(
            graph_error(503, "ServiceUnavailable", headers={"retry-after": "30"}), TransientEmailDeliveryError
        )

        self.assertEqual(
            (attempt.error_kind, attempt.retry_after_seconds, email.status), ("server_busy", 30, Status.FAILED)
        )

    def test_a_full_sender_mailbox_is_a_mailbox_restriction(self):
        _email, attempt = self.send_failing(graph_error(507))

        self.assertEqual((attempt.http_status, attempt.error_kind), (507, "mailbox_restricted"))

    def test_a_refused_token_request_is_an_authentication_failure_at_the_token_step(self):
        token_answer = HttpResponse(
            401,
            {"x-ms-request-id": REQUEST_ID},
            json.dumps({"error": "invalid_client", "error_codes": [7000215], "error_description": BODY_TEXT}).encode(),
        )
        self.fake.script(token=token_answer, send=accepted())

        with self.assertRaises(PermanentEmailDeliveryError):
            self.send()

        email = self.only_email()
        attempt = email.attempts.get()
        self.assertEqual((attempt.operation, attempt.http_status, attempt.error_kind), ("token", 401, "auth"))
        self.assertEqual(attempt.error_code, "invalid_client AADSTS7000215")
        self.assertEqual((attempt.request_id, email.status), (REQUEST_ID, Status.FAILED))
        self.assertEqual(self.fake.send_requests, [])

    def test_a_connection_failure_is_an_api_failure_that_sent_nothing(self):
        email, attempt = self.send_failing(transport.ConnectFailed(), TransientEmailDeliveryError)

        self.assertEqual(
            (attempt.error_kind, attempt.http_status, email.status), ("connect_failed", None, Status.FAILED)
        )
        self.assertTrue(attempt.client_request_id)

    def test_a_timeout_after_the_request_began_leaves_the_outcome_unknown(self):
        lost = transport.ResponseLost()
        lost.__cause__ = TimeoutError("timed out")

        email, attempt = self.send_failing(lost, UncertainEmailDeliveryError)

        self.assertEqual(
            (attempt.outcome, attempt.error_kind, email.status), (Outcome.UNCERTAIN, "timeout", Status.UNCERTAIN)
        )

    def test_no_body_text_token_or_key_is_ever_stored(self):
        self.send_failing(graph_error(400, "ErrorInvalidRecipients", inner="ErrorInvalidRecipients"))

        stored = stored_text()
        for secret in (BODY_TEXT, ACCESS_TOKEN, KEY_LINE, "Bearer"):
            self.assertNotIn(secret, stored)


class RetryAndDeferralTests(TelemetryTestCase):
    def test_every_retry_under_one_retry_key_is_an_attempt_of_one_email(self):
        self.fake.script(send=[graph_error(429, headers={"retry-after": "5"}), accepted()])

        with self.assertRaises(TransientEmailDeliveryError):
            self.send(retry_key="core.backgroundjob:1")
        self.clock.advance(120)
        self.send(retry_key="core.backgroundjob:1")

        email = self.only_email()
        attempts = list(email.attempts.order_by("attempt_number"))
        self.assertEqual(
            [(a.attempt_number, a.outcome) for a in attempts], [(1, Outcome.TRANSIENT), (2, Outcome.ACCEPTED)]
        )
        self.assertEqual((email.status, email.attempt_count, email.retry_count), (Status.ACCEPTED, 2, 1))
        self.assertEqual(email.last_error_kind, "throttled")

    def test_sends_without_a_retry_key_are_separate_emails(self):
        self.fake.script(send=accepted())

        self.send()
        self.send()

        self.assertEqual(OutboundEmail.objects.count(), 2)

    def test_a_different_message_under_the_same_key_is_another_email(self):
        self.fake.script(send=accepted())

        self.send(retry_key="core.backgroundjob:1")
        self.send(
            EmailMessage(subject="Other", to=("person@example.com",), html_body="<p>x</p>"),
            retry_key="core.backgroundjob:1",
        )

        self.assertEqual(OutboundEmail.objects.count(), 2)

    def deferred(self):
        now = timezone.now()
        return RateDeferred(now + timedelta(seconds=30), "pace", now=now)

    def test_a_deferral_with_a_retry_key_stays_pending_and_records_no_attempt(self):
        with patch("apps.core.services.email.delivery.admit", side_effect=self.deferred()):
            with self.assertRaises(EmailRateDeferred):
                self.send(retry_key="mail.recipientlog:1")

        email = self.only_email()
        self.assertEqual((email.status, email.deferral_count, email.attempt_count), (Status.PENDING, 1, 0))
        self.assertEqual(email.last_error_kind, "rate_deferred")

    def test_a_deferral_nobody_retries_is_not_sent(self):
        with patch("apps.core.services.email.delivery.admit", side_effect=self.deferred()):
            with self.assertRaises(EmailRateDeferred):
                self.send()

        self.assertEqual(self.only_email().status, Status.NOT_SENT)

    def test_a_refusal_by_the_delivery_limits_is_not_sent(self):
        with patch("apps.core.services.email.delivery.admit", side_effect=RateRefused("daily")):
            with self.assertRaises(PermanentEmailDeliveryError):
                self.send()

        email = self.only_email()
        self.assertEqual((email.status, email.last_error_kind), (Status.NOT_SENT, "rate_refused"))

    def test_an_inactive_configuration_is_not_sent_and_records_why(self):
        self.service_config.is_active = False

        with self.assertRaises(PermanentEmailDeliveryError):
            self.send()

        email = self.only_email()
        self.assertEqual((email.status, email.last_error_kind), (Status.NOT_SENT, "config"))
        self.assertIn("No active email service configuration", email.last_error)

    def test_a_job_claim_lost_before_the_provider_call_is_not_sent(self):
        def lose_claim():
            raise JobClaimLost("Background job claim was lost before the email provider call.")

        with self.assertRaises(JobClaimLost):
            deliver_email(
                EmailMessage(subject="Hello", to=("person@example.com",), html_body="<p>x</p>"),
                config=self.service_config,
                before_provider_call=lose_claim,
            )

        email = self.only_email()
        attempt = email.attempts.get()
        self.assertEqual((attempt.outcome, attempt.error_kind), (Outcome.NOT_SENT, "claim_lost"))
        self.assertEqual(email.status, Status.NOT_SENT)
        self.assertEqual(self.fake.send_requests, [])

    def test_a_background_job_files_its_email_under_the_job(self):
        self.fake.script(send=accepted())
        job = SimpleNamespace(pk="5b8d9c1e-0000-4000-8000-000000000001", kind="authn.notification_email", attempts=2)

        with job_tracking(job):
            self.send()

        email = self.only_email()
        self.assertEqual(str(email.job_id), job.pk)
        self.assertEqual(email.attempts.get().job_attempt, 2)


class ResilienceTests(TelemetryTestCase):
    def test_a_telemetry_database_error_never_stops_the_send(self):
        self.fake.script(send=accepted())

        with patch.object(OutboundEmail.objects, "get_or_create", side_effect=DatabaseError("down")):
            with self.assertLogs("apps.core.services.email.telemetry.recorder", "WARNING"):
                result = self.send()

        self.assertEqual(result.provider, "graph")
        self.assertEqual(len(self.fake.send_requests), 1)
        self.assertFalse(OutboundEmail.objects.exists())

    def test_a_telemetry_error_never_changes_the_error_a_failed_send_raises(self):
        self.fake.script(send=graph_error(400, "ErrorInvalidRecipients"))

        with patch.object(OutboundEmailAttempt.objects, "create", side_effect=DatabaseError("down")):
            with self.assertRaisesMessage(PermanentEmailDeliveryError, "ErrorInvalidRecipients"):
                self.send()

    @monitoring_settings(telemetry_enabled=False)
    def test_switched_off_it_records_nothing(self):
        self.fake.script(send=accepted())

        self.send()

        self.assertFalse(OutboundEmail.objects.exists())

    def test_with_subjects_switched_off_only_the_digest_is_kept(self):
        self.fake.script(send=accepted())

        with monitoring_settings(store_subjects=False):
            self.send()

        email = self.only_email()
        self.assertEqual(email.subject, "")
        self.assertEqual(len(email.subject_digest), 64)
