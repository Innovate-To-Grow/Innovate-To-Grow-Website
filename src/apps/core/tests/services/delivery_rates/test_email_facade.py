"""Every email goes through the delivery-rate limiter: ``deliver_email`` admits, waits, sends, records."""

import smtplib
from datetime import timedelta
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.db import transaction
from django.test import TestCase

from apps.core.models import AWSCredentialConfig, DeliveryRateState, EmailServiceConfig, SMTPProviderConfig
from apps.core.services import delivery_rates as rates
from apps.core.services.background_jobs import JobClaimLost
from apps.core.services.email import (
    EmailMessage,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    deliver_email,
)
from apps.core.services.email.exceptions import EmailRateDeferred
from apps.core.services.email.registry import active_rate_target

from .helpers import FakeClock, spy_on_email_admissions

SES_CLIENT = "apps.core.services.email.ses.boto3.client"


def message(**overrides):
    values = {"subject": "Hi", "to": ("a@example.com",), "cc": ("b@example.com",), "text_body": "Body"}
    return EmailMessage(**values | overrides)


def ses_error(code, text=""):
    return ClientError({"Error": {"Code": code, "Message": text}}, "SendRawEmail")


class SesThroughTheLimiterTests(TestCase):
    def setUp(self):
        self.clock = FakeClock().install(self)
        self.aws = AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        self.config = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu"
        )
        self.identity = rates.ses_identity(self.aws.pk, "us-west-2")
        patcher = patch(SES_CLIENT)
        self.factory = patcher.start()
        self.client = self.factory.return_value
        self.addCleanup(patcher.stop)
        self.client.send_raw_email.return_value = {"MessageId": "ses-1"}

    def state(self):
        return DeliveryRateState.objects.get(channel="ses_send", identity=self.identity)

    def test_a_send_is_admitted_on_the_ses_account_and_region_and_counts_every_recipient(self):
        deliver_email(message(), config=self.config)

        state = self.state()
        self.assertEqual((state.cooldown_group, state.last_signal), ("ses:us-west-2", rates.SignalKind.OK))
        self.assertEqual(state.usage_buckets.get().total, 2)
        self.assertEqual(active_rate_target(), ("ses_send", self.identity))

    def test_a_held_back_message_never_reaches_the_callback_or_ses(self):
        DeliveryRateState.objects.create(
            channel="ses_send",
            identity=self.identity,
            cooldown_group="ses:us-west-2",
            cooldown_until=self.clock.now() + timedelta(minutes=5),
        )
        callback = MagicMock()

        with self.assertRaises(EmailRateDeferred) as caught:
            deliver_email(message(), config=self.config, before_provider_call=callback)

        callback.assert_not_called()
        self.client.send_raw_email.assert_not_called()
        self.assertGreater(caught.exception.retry_after, 10)
        self.assertIsInstance(caught.exception, TransientEmailDeliveryError)

    def test_a_throttle_cools_the_account_down_and_slows_smart_rate(self):
        self.client.send_raw_email.side_effect = ses_error("Throttling", "Maximum sending rate exceeded.")

        with self.assertRaises(TransientEmailDeliveryError):
            deliver_email(message(), config=self.config)

        state = self.state()
        self.assertGreater(state.cooldown_until, self.clock.now())
        self.assertEqual((state.last_signal, state.factor_base), (rates.SignalKind.THROTTLE, 0.25))
        self.assertFalse(state.usage_buckets.get().total)  # the message was not taken

    def test_a_paused_account_stops_mail_without_failing_it_for_good(self):
        self.client.send_raw_email.side_effect = ses_error("AccountSendingPausedException", "Sending paused.")

        with self.assertRaises(TransientEmailDeliveryError) as first:
            deliver_email(message(), config=self.config)
        for _attempt in range(3):
            with self.assertRaises(EmailRateDeferred):
                deliver_email(message(), config=self.config)

        self.assertEqual(first.exception.rate_signal.reason, rates.Reason.ACCOUNT_PAUSED)
        self.assertEqual(self.client.send_raw_email.call_count, 1)
        self.assertEqual(self.state().breaker_reason, rates.Reason.ACCOUNT_PAUSED)

    def test_a_failure_before_ses_was_reached_gives_the_slot_back(self):
        with self.assertRaises(PermanentEmailDeliveryError):
            deliver_email(message(headers={"From": "spoof@example.com"}), config=self.config)

        state = self.state()
        self.assertIsNone(state.tat)
        self.assertFalse(state.usage_buckets.filter(total__gt=0).exists())

    def test_a_lost_job_claim_gives_the_slot_back_and_propagates(self):
        def claim_lost():
            raise JobClaimLost("lost")

        with self.assertRaises(JobClaimLost):
            deliver_email(message(), config=self.config, before_provider_call=claim_lost)

        self.assertIsNone(self.state().tat)
        self.client.send_raw_email.assert_not_called()

    def test_ses_is_called_with_one_attempt_by_default(self):
        deliver_email(message(), config=self.config)

        config = self.factory.call_args.kwargs["config"]
        self.assertEqual(config.retries, {"total_max_attempts": 1, "mode": "standard"})

    def test_admission_inside_a_callers_transaction_is_refused_in_tests(self):
        with self.assertRaises(rates.AdmissionInTransaction), transaction.atomic():
            deliver_email(message(), config=self.config)

    def test_campaigns_pass_the_bulk_lane(self):
        deliver_email(message(), config=self.config, lane=rates.Lane.BULK)

        self.assertEqual(self.state().usage_buckets.get().bulk, 2)


@patch("smtplib.SMTP")
class SmtpThroughTheLimiterTests(TestCase):
    def setUp(self):
        FakeClock().install(self)
        SMTPProviderConfig.objects.create(
            name="Relay",
            is_active=True,
            host="smtp-relay.gmail.com",
            port=587,
            username="i2g@example.edu",
            password="app-password",  # noqa: S106 - a test fixture, never sent anywhere
        )
        self.config = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="smtp", from_email="i2g@example.edu"
        )

    def state(self):
        return DeliveryRateState.objects.get(channel="smtp_send", identity="smtp-relay.gmail.com:587:i2g@example.edu")

    def test_a_daily_limit_reply_stops_sending_and_is_retried_later_not_failed(self, smtp_class):
        smtp_class.return_value.send_message.side_effect = smtplib.SMTPDataError(
            550, b"5.4.5 Daily user sending limit exceeded."
        )

        with self.assertRaises(TransientEmailDeliveryError) as caught:
            deliver_email(message(), config=self.config)

        self.assertEqual(caught.exception.rate_signal.kind, rates.SignalKind.QUOTA)
        self.assertEqual(self.state().breaker_state, DeliveryRateState.BreakerState.OPEN)
        with self.assertRaises(EmailRateDeferred):
            deliver_email(message(), config=self.config)

    def test_a_recipient_receiving_too_fast_is_about_that_message_only(self, smtp_class):
        smtp_class.return_value.send_message.side_effect = smtplib.SMTPDataError(
            550, b"5.2.1 The email account that you tried to reach is receiving mail at a rate that prevents delivery"
        )

        with self.assertRaises(PermanentEmailDeliveryError):
            deliver_email(message(), config=self.config)

        state = self.state()
        self.assertIsNone(state.cooldown_until)
        self.assertEqual(state.breaker_state, DeliveryRateState.BreakerState.CLOSED)

    def test_refused_credentials_open_the_auth_breaker(self, smtp_class):
        smtp_class.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Bad credentials")

        with self.assertRaises(PermanentEmailDeliveryError):
            deliver_email(message(), config=self.config)

        self.assertEqual(self.state().breaker_reason, rates.Reason.AUTH)


class AdminTestSendTests(TestCase):
    def setUp(self):
        FakeClock().install(self)
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        self.config = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu"
        )

    @patch(SES_CLIENT)
    def test_the_admin_test_email_is_admitted_on_the_transactional_lane(self, factory):
        from apps.core.admin.service_credentials.helpers import _send_test_email

        factory.return_value.send_raw_email.return_value = {"MessageId": "ses-1"}
        admissions = spy_on_email_admissions(self)

        self.assertEqual(_send_test_email(config=self.config, recipient="me@example.edu"), "AWS SES")
        self.assertEqual(admissions.call_args.kwargs["lane"], rates.Lane.TRANSACTIONAL)
