from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.db import DatabaseError
from django.utils import timezone

from apps.core.models import OutboundEmail, OutboundEmailAttempt
from apps.core.services.background_jobs import JobClaimLost
from apps.core.services.delivery_rates import RateDeferred, RateRefused
from apps.core.services.email import (
    EmailMessage,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    deliver_email,
)
from apps.core.services.email.exceptions import EmailRateDeferred
from apps.core.services.email.telemetry import job_tracking
from apps.core.tests.services.email_monitoring.telemetry.test_telemetry_graph_send import (
    Outcome,
    Status,
    TelemetryTestCase,
)

from ..helpers import accepted, graph_error, monitoring_settings


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
