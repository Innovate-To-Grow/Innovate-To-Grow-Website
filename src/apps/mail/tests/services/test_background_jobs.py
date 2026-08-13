import threading
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import Mock, patch

from botocore.exceptions import ReadTimeoutError
from django.db import OperationalError, close_old_connections, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.authn.services.sms import PhoneVerificationInvalid, PhoneVerificationThrottled
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    claim_jobs,
    process_claimed_job,
    recover_stale_jobs,
    retry_job,
)
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign, SmsRecipientLog
from apps.mail.services.campaign.dispatch import (
    _mark_email_processing,
    _mark_sms_processing,
    _run_in_process_email_campaign,
    _run_in_process_sms_campaign,
    _send_via_sms,
    aggregate_email_campaign,
    aggregate_sms_campaign,
    dispatch_email_campaign,
    dispatch_sms_campaign,
    queue_email_campaign,
    queue_sms_campaign,
    resolve_stale_delivery_job,
    sync_delivery_job_state,
)
from apps.mail.services.campaign.state import campaign_state
from apps.mail.services.send_campaign import SesSendResult
from apps.mail.services.send_campaign.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_TRANSIENT,
)


def _provider_failure(exc):
    def fail(*, before_provider_call, **_kwargs):
        before_provider_call()
        raise exc

    return fail


class CampaignStateTests(SimpleTestCase):
    def test_campaign_state_covers_empty_active_and_terminal_counts(self):
        cases = [
            ({"total": 0, "sent": 0, "failed": 0}, "sent"),
            ({"total": 3, "sent": 0, "failed": 0, "active": 3}, "queued"),
            ({"total": 3, "sent": 1, "failed": 0, "active": 2}, "sending"),
            ({"total": 3, "sent": 0, "failed": 1, "active": 2}, "sending"),
            ({"total": 3, "sent": 3, "failed": 0}, "sent"),
            ({"total": 3, "sent": 1, "failed": 2}, "partial"),
            ({"total": 3, "sent": 0, "failed": 3}, "failed"),
        ]

        for counts, expected in cases:
            with self.subTest(counts=counts):
                self.assertEqual(campaign_state(**counts), expected)


@override_settings(BACKGROUND_JOBS_ENABLED=False)
class InProcessCampaignDispatchTests(TestCase):
    def setUp(self):
        self.sender = make_superuser()

    @patch("apps.mail.services.campaign.dispatch.start_in_process_task")
    def test_email_dispatch_returns_without_provider_io(self, start_task):
        campaign = EmailCampaign.objects.create(
            name="Legacy email",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="person@example.com",
        )

        result = dispatch_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 0, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "sending")
        self.assertEqual(campaign.sent_by, self.sender)
        self.assertFalse(RecipientLog.objects.filter(campaign=campaign).exists())
        start_task.assert_called_once_with(
            _run_in_process_email_campaign,
            campaign.pk,
            self.sender.pk,
            name=f"email-campaign-{campaign.pk}",
            daemon=False,
        )

    @patch("apps.mail.services.campaign.dispatch.start_in_process_task")
    def test_sms_dispatch_returns_without_provider_io(self, start_task):
        campaign = SmsCampaign.objects.create(
            name="Legacy SMS",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101",
        )

        result = dispatch_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 0, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "sending")
        self.assertEqual(campaign.sent_by, self.sender)
        self.assertFalse(SmsRecipientLog.objects.filter(campaign=campaign).exists())
        start_task.assert_called_once_with(
            _run_in_process_sms_campaign,
            campaign.pk,
            self.sender.pk,
            name=f"sms-campaign-{campaign.pk}",
            daemon=False,
        )

    @patch(
        "apps.mail.services.campaign.dispatch.start_in_process_task",
        side_effect=RuntimeError("can't start new thread"),
    )
    def test_email_start_failure_is_persisted_and_propagated(self, _start_task):
        campaign = EmailCampaign.objects.create(
            name="Legacy email startup failure",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="person@example.com",
        )

        with self.assertRaisesMessage(RuntimeError, "can't start new thread"):
            dispatch_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertIn("could not be started", campaign.error_message)

    @patch(
        "apps.mail.services.campaign.dispatch.start_in_process_task",
        side_effect=RuntimeError("can't start new thread"),
    )
    def test_sms_start_failure_is_persisted_and_propagated(self, _start_task):
        campaign = SmsCampaign.objects.create(
            name="Legacy SMS startup failure",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101",
        )

        with self.assertRaisesMessage(RuntimeError, "can't start new thread"):
            dispatch_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertIn("could not be started", campaign.error_message)


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class DurableCampaignQueueTests(TestCase):
    def setUp(self):
        self.sender = make_superuser()

    def test_email_campaign_materializes_one_log_and_job_per_recipient(self):
        campaign = EmailCampaign.objects.create(
            name="Durable email",
            subject="Hello",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="one@example.com\ntwo@example.com",
        )

        result = queue_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 2, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "queued")
        self.assertEqual(campaign.total_recipients, 2)
        self.assertEqual(RecipientLog.objects.filter(campaign=campaign).count(), 2)
        self.assertEqual(
            BackgroundJob.objects.filter(kind="mail.email_recipient").count(),
            2,
        )
        with self.assertRaisesMessage(ValueError, "no longer in draft"):
            queue_email_campaign(campaign, sent_by=self.sender)
        self.assertEqual(BackgroundJob.objects.filter(kind="mail.email_recipient").count(), 2)

    def test_sms_campaign_materializes_one_log_and_job_per_recipient(self):
        campaign = SmsCampaign.objects.create(
            name="Durable SMS",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101\n+12095550102",
        )

        result = queue_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result["total"], 2)
        self.assertEqual(campaign.status, "queued")
        self.assertEqual(SmsRecipientLog.objects.filter(campaign=campaign).count(), 2)
        self.assertEqual(
            BackgroundJob.objects.filter(kind="mail.sms_recipient").count(),
            2,
        )

    def _queued_email(self):
        campaign = EmailCampaign.objects.create(
            name="Worker email",
            subject="Hello {{first_name}}",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=self.sender)
        return campaign, RecipientLog.objects.get(campaign=campaign)

    def _queued_sms(self):
        campaign = SmsCampaign.objects.create(
            name="Worker SMS",
            message="Hello {{first_name}}",
            audience_type="manual",
            manual_phones="+12095550101",
        )
        queue_sms_campaign(campaign, sent_by=self.sender)
        return campaign, SmsRecipientLog.objects.get(campaign=campaign)

    @patch("apps.mail.services.campaign.dispatch._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch._send_via_ses",
        return_value=SesSendResult(message_id="ses-123"),
    )
    @patch("apps.mail.services.campaign.dispatch._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load")
    def test_successful_provider_result_completes_job_log_and_campaign(
        self,
        load_config,
        _get_client,
        _send,
        _context,
        _unsubscribe,
    ):
        load_config.return_value = Mock(
            source_address="Sender <sender@example.com>",
            ses_configuration_set_name="",
        )
        campaign, log = self._queued_email()
        job = claim_jobs()[0]

        self.assertTrue(process_claimed_job(job))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.provider_message_id, "ses-123")
        self.assertEqual(campaign.status, "sent")
        self.assertEqual(campaign.sent_count, 1)

    @patch("apps.mail.services.campaign.dispatch._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch._recipient_context", return_value={})
    @patch("apps.mail.services.campaign.dispatch._send_via_ses")
    @patch("apps.mail.services.campaign.dispatch._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load")
    def test_ses_acceptance_with_lost_recipient_claim_is_uncertain(
        self,
        load_config,
        _get_client,
        send,
        _context,
        _unsubscribe,
    ):
        load_config.return_value = Mock(
            source_address="Sender <sender@example.com>",
            ses_configuration_set_name="",
        )
        campaign, log = self._queued_email()

        def accept_after_claim_loss(**_kwargs):
            RecipientLog.objects.filter(pk=log.pk).update(claim_token=BackgroundJob.new_claim_token())
            return SesSendResult(message_id="ses-accepted")

        send.side_effect = accept_after_claim_loss

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.email_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(log.provider_message_id, "")
        self.assertEqual(campaign.status, "failed")

    @patch("apps.mail.services.campaign.dispatch.wait_for_delivery_slot")
    @patch("apps.mail.services.campaign.dispatch._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch._send_via_ses",
        return_value=SesSendResult(message_id="ses-rate"),
    )
    @patch("apps.mail.services.campaign.dispatch._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load")
    def test_worker_reserves_shared_configured_ses_rate(
        self,
        load_config,
        _get_client,
        _send,
        _context,
        _unsubscribe,
        wait_for_slot,
    ):
        load_config.return_value = Mock(
            source_address="Sender <sender@example.com>",
            provider="ses",
            ses_configuration_set_name="",
            max_send_rate=7,
        )
        self._queued_email()

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        wait_for_slot.assert_called_once_with("ses", 7.0)

    @patch(
        "apps.mail.services.campaign.dispatch._get_ses_client",
        side_effect=OperationalError("database temporarily unavailable"),
    )
    @patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load", return_value=Mock())
    def test_transient_failure_before_provider_sets_log_to_retry(
        self,
        _load_config,
        _get_client,
    ):
        campaign, log = self._queued_email()
        job = claim_jobs()[0]

        self.assertFalse(process_claimed_job(job))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(log.status, "retry")
        self.assertEqual(campaign.status, "queued")
        self.assertGreater(job.available_at, timezone.now())

    @patch("apps.mail.services.campaign.dispatch._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch._send_via_ses",
        return_value=SesSendResult(error="timeout"),
    )
    @patch("apps.mail.services.campaign.dispatch._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load")
    def test_unknown_provider_outcome_is_quarantined_without_auto_retry(
        self,
        load_config,
        _get_client,
        _send,
        _context,
        _unsubscribe,
    ):
        load_config.return_value = Mock(
            source_address="Sender <sender@example.com>",
            ses_configuration_set_name="",
        )
        campaign, log = self._queued_email()
        job = claim_jobs()[0]

        self.assertFalse(process_claimed_job(job))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(campaign.status, "failed")
        self.assertIsNotNone(log.uncertain_at)

    @patch("apps.mail.services.campaign.dispatch._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch._send_via_ses",
        return_value=SesSendResult(
            error="SES temporarily rejected the request.",
            outcome=SES_OUTCOME_TRANSIENT,
        ),
    )
    @patch("apps.mail.services.campaign.dispatch._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load")
    def test_definitive_ses_throttle_retries_safely(
        self,
        load_config,
        _get_client,
        _send,
        _context,
        _unsubscribe,
    ):
        load_config.return_value = Mock(
            source_address="Sender <sender@example.com>",
            ses_configuration_set_name="",
            ses_max_send_rate=0,
        )
        campaign, log = self._queued_email()

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.email_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(log.status, "retry")
        self.assertEqual(campaign.status, "queued")

    @patch("apps.mail.services.campaign.dispatch._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch._send_via_ses",
        return_value=SesSendResult(
            error="SES rejected the request.",
            outcome=SES_OUTCOME_PERMANENT,
        ),
    )
    @patch("apps.mail.services.campaign.dispatch._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load")
    def test_definitive_ses_rejection_fails_without_uncertain_state(
        self,
        load_config,
        _get_client,
        _send,
        _context,
        _unsubscribe,
    ):
        load_config.return_value = Mock(
            source_address="Sender <sender@example.com>",
            ses_configuration_set_name="",
            ses_max_send_rate=0,
        )
        campaign, log = self._queued_email()

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.email_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(log.status, "failed")
        self.assertEqual(campaign.status, "failed")

    @patch(
        "apps.mail.services.campaign.dispatch._send_via_sms",
        side_effect=_provider_failure(PhoneVerificationThrottled("slow down")),
    )
    @patch(
        "apps.mail.services.campaign.dispatch.AWSCredentialConfig.load",
        return_value=Mock(sns_configured=True),
    )
    def test_definitive_sms_throttle_retries_safely(self, _config, _publish):
        campaign, log = self._queued_sms()

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.sms_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(log.status, "retry")
        self.assertEqual(campaign.status, "queued")

    @patch(
        "apps.mail.services.campaign.dispatch._send_via_sms",
        side_effect=_provider_failure(PhoneVerificationInvalid("invalid phone")),
    )
    @patch(
        "apps.mail.services.campaign.dispatch.AWSCredentialConfig.load",
        return_value=Mock(sns_configured=True),
    )
    def test_definitive_sms_validation_failure_is_permanent(self, _config, _publish):
        campaign, log = self._queued_sms()

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.sms_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(log.status, "failed")
        self.assertEqual(campaign.status, "failed")

    @patch(
        "apps.mail.services.campaign.dispatch._send_via_sms",
        side_effect=_provider_failure(ReadTimeoutError(endpoint_url="https://sms-voice.us-west-2.amazonaws.com")),
    )
    @patch(
        "apps.mail.services.campaign.dispatch.AWSCredentialConfig.load",
        return_value=Mock(sns_configured=True),
    )
    def test_sms_lost_response_is_uncertain(self, _config, _send):
        campaign, log = self._queued_sms()

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.sms_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(campaign.status, "failed")

    @patch("apps.mail.services.campaign.dispatch._send_via_sms")
    @patch(
        "apps.mail.services.campaign.dispatch.AWSCredentialConfig.load",
        return_value=Mock(sns_configured=True),
    )
    def test_sns_acceptance_with_lost_recipient_claim_is_uncertain(self, _config, send):
        campaign, log = self._queued_sms()

        def accept_after_claim_loss(*, before_provider_call, **_kwargs):
            before_provider_call()
            SmsRecipientLog.objects.filter(pk=log.pk).update(claim_token=BackgroundJob.new_claim_token())
            return "sns-accepted"

        send.side_effect = accept_after_claim_loss

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.sms_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(log.sns_message_id, "")
        self.assertEqual(campaign.status, "failed")

    @patch("apps.mail.services.campaign.dispatch.boto3.client")
    @patch("apps.mail.services.campaign.dispatch.resolve_aws_credentials")
    def test_sms_transport_disables_sdk_retries_and_marks_provider_boundary(
        self,
        resolve_credentials,
        boto_client,
    ):
        resolve_credentials.return_value = Mock(
            region="us-west-2",
            access_key_id="key",
            secret_access_key="secret",
        )
        boto_client.return_value.send_text_message.return_value = {
            "MessageId": "sms-123",
        }
        before_provider_call = Mock()
        config = Mock()
        config.resolved_sms_from_number.return_value = "+12095550199"

        message_id = _send_via_sms(
            config=config,
            phone_number="+12095550101",
            message="Hello",
            before_provider_call=before_provider_call,
        )

        self.assertEqual(message_id, "sms-123")
        self.assertEqual(
            boto_client.call_args.kwargs["config"].retries["total_max_attempts"],
            1,
        )
        before_provider_call.assert_called_once_with()

    def test_stale_claim_after_recorded_send_is_completed_not_resent(self):
        campaign, log = self._queued_email()
        job = claim_jobs()[0]
        stale_at = timezone.now() - timedelta(hours=1)
        RecipientLog.objects.filter(pk=log.pk).update(
            status="sent",
            sent_at=stale_at,
            provider_message_id="known-provider-id",
        )
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            provider_call_started_at=stale_at,
        )

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(result["completed"], 1)
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(log.status, "sent")
        self.assertEqual(campaign.status, "sent")
        self.assertEqual(campaign.sent_count, 1)
        self.assertIsNotNone(campaign.sent_at)

    def test_successful_recovery_rolls_back_when_campaign_mirror_fails(self):
        campaign, log = self._queued_email()
        job = claim_jobs()[0]
        stale_at = timezone.now() - timedelta(hours=1)
        RecipientLog.objects.filter(pk=log.pk).update(
            status="sent",
            sent_at=stale_at,
            provider_message_id="known-provider-id",
        )
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            provider_call_started_at=stale_at,
        )

        with patch(
            "apps.mail.services.campaign.dispatch.aggregate_email_campaign",
            side_effect=OperationalError("aggregate unavailable"),
        ):
            result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(result, {"completed": 0, "retried": 0, "failed": 0, "uncertain": 0})
        self.assertEqual(job.status, BackgroundJob.Status.PROCESSING)
        self.assertIsNotNone(job.claim_token)
        self.assertEqual(log.status, "sent")
        self.assertEqual(campaign.status, "queued")

        retry_result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(retry_result["completed"], 1)
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(campaign.status, "sent")

    def test_stale_delivery_at_max_attempts_fails_recipient_and_campaign(self):
        campaign, log = self._queued_email()
        job = claim_jobs()[0]
        stale_at = timezone.now() - timedelta(hours=1)
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            max_attempts=job.attempts,
        )

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertIn("Maximum attempts", job.last_error)
        self.assertEqual(log.status, "failed")
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(campaign.failed_count, 1)

    def test_stale_claim_preserves_terminal_provider_failure(self):
        campaign, log = self._queued_email()
        job = claim_jobs()[0]
        stale_at = timezone.now() - timedelta(hours=1)
        RecipientLog.objects.filter(pk=log.pk).update(
            status="bounced",
            bounced_at=stale_at,
        )
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            provider_call_started_at=stale_at,
        )

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(log.status, "bounced")
        self.assertEqual(campaign.status, "failed")

    @patch("apps.mail.services.campaign.dispatch._send_via_ses")
    def test_terminal_email_recipient_is_not_sent_again(self, send):
        campaign, log = self._queued_email()
        RecipientLog.objects.filter(pk=log.pk).update(
            status="complained",
            complained_at=timezone.now(),
        )

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.email_recipient")
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        send.assert_not_called()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(log.status, "complained")
        self.assertEqual(campaign.status, "failed")

    def test_stale_claim_during_provider_call_becomes_uncertain_until_manual_retry(self):
        campaign, log = self._queued_email()
        job = claim_jobs()[0]
        stale_at = timezone.now() - timedelta(hours=1)
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            provider_call_started_at=stale_at,
        )

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(result["uncertain"], 1)
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(campaign.status, "failed")

        self.assertTrue(retry_job(job))
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(log.status, "retry")
        self.assertEqual(campaign.status, "queued")

    def test_manual_retry_and_recipient_mirror_roll_back_together(self):
        campaign, log = self._queued_email()
        job = claim_jobs()[0]
        completed_at = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk).update(
            status=BackgroundJob.Status.UNCERTAIN,
            claim_token=None,
            claimed_at=None,
            completed_at=completed_at,
            last_error="Review delivery",
        )
        RecipientLog.objects.filter(pk=log.pk).update(
            status="uncertain",
            claim_token=None,
            claimed_at=None,
            uncertain_at=completed_at,
        )
        aggregate_email_campaign(campaign.pk)
        job.refresh_from_db()

        with (
            patch(
                "apps.mail.services.campaign.dispatch.aggregate_email_campaign",
                side_effect=OperationalError("aggregate unavailable"),
            ),
            self.assertRaisesMessage(OperationalError, "aggregate unavailable"),
        ):
            retry_job(job)

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(claim_jobs(), [])

        self.assertTrue(retry_job(job))
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(log.status, "retry")
        self.assertEqual(campaign.status, "queued")

    def test_manual_sms_retry_updates_recipient_and_campaign(self):
        campaign, log = self._queued_sms()
        job = claim_jobs()[0]
        completed_at = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk).update(
            status=BackgroundJob.Status.UNCERTAIN,
            claim_token=None,
            claimed_at=None,
            completed_at=completed_at,
            last_error="Review delivery",
        )
        SmsRecipientLog.objects.filter(pk=log.pk).update(
            status="uncertain",
            claim_token=None,
            claimed_at=None,
            uncertain_at=completed_at,
        )
        aggregate_sms_campaign(campaign.pk)
        job.refresh_from_db()

        self.assertTrue(retry_job(job))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertIsNone(job.completed_at)
        self.assertEqual(job.last_error, "")
        self.assertEqual(log.status, "retry")
        self.assertIsNone(log.uncertain_at)
        self.assertEqual(campaign.status, "queued")

    def test_stale_worker_cannot_replace_new_email_recipient_claim(self):
        _campaign, log = self._queued_email()
        stale_job = claim_jobs()[0]
        new_token = BackgroundJob.new_claim_token()
        BackgroundJob.objects.filter(pk=stale_job.pk).update(claim_token=new_token)
        RecipientLog.objects.filter(pk=log.pk).update(
            status="processing",
            claim_token=new_token,
            claimed_at=timezone.now(),
        )

        self.assertFalse(_mark_email_processing(log, stale_job))

        log.refresh_from_db()
        self.assertEqual(log.status, "processing")
        self.assertEqual(log.claim_token, new_token)

    def test_stale_state_mirror_cannot_clear_new_sms_recipient_claim(self):
        _campaign, log = self._queued_sms()
        stale_job = claim_jobs()[0]
        BackgroundJob.objects.filter(pk=stale_job.pk).update(
            status=BackgroundJob.Status.RETRY,
            claim_token=None,
            claimed_at=None,
        )
        stale_job.refresh_from_db()
        new_token = BackgroundJob.new_claim_token()
        BackgroundJob.objects.filter(pk=stale_job.pk).update(
            status=BackgroundJob.Status.PROCESSING,
            claim_token=new_token,
            claimed_at=timezone.now(),
        )
        SmsRecipientLog.objects.filter(pk=log.pk).update(
            status="processing",
            claim_token=new_token,
            claimed_at=timezone.now(),
        )

        sync_delivery_job_state(stale_job)

        log.refresh_from_db()
        self.assertEqual(log.status, "processing")
        self.assertEqual(log.claim_token, new_token)

    def test_sms_processing_requires_current_durable_claim(self):
        _campaign, log = self._queued_sms()
        stale_job = claim_jobs()[0]
        new_token = BackgroundJob.new_claim_token()
        BackgroundJob.objects.filter(pk=stale_job.pk).update(claim_token=new_token)

        self.assertFalse(_mark_sms_processing(log, stale_job))

        log.refresh_from_db()
        self.assertEqual(log.status, "pending")
        self.assertIsNone(log.claim_token)

    def test_campaign_status_is_aggregated_from_recipient_logs(self):
        campaign = EmailCampaign.objects.create(
            name="Partial",
            subject="Subject",
            body="Body",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="sent@example.com",
            status="sent",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="uncertain@example.com",
            status="uncertain",
        )

        aggregate_email_campaign(campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "partial")
        self.assertEqual(campaign.total_recipients, 2)
        self.assertEqual(campaign.sent_count, 1)
        self.assertEqual(campaign.failed_count, 1)

    def test_email_aggregation_locks_campaign_and_preserves_terminal_sent_at(self):
        sent_at = timezone.now() - timedelta(hours=2)
        campaign = EmailCampaign.objects.create(
            name="Stable email timestamp",
            subject="Subject",
            body="Body",
            status="sent",
            sent_at=sent_at,
        )
        log = RecipientLog.objects.create(
            campaign=campaign,
            email_address="sent@example.com",
            status="sent",
        )

        with patch.object(
            EmailCampaign.objects,
            "select_for_update",
            wraps=EmailCampaign.objects.select_for_update,
        ) as lock_campaign:
            aggregate_email_campaign(campaign.pk)

        lock_campaign.assert_called_once_with()
        campaign.refresh_from_db()
        self.assertEqual(campaign.sent_at, sent_at)

        log.status = "bounced"
        log.save(update_fields=["status", "updated_at"])
        aggregate_email_campaign(campaign.pk)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(campaign.sent_at, sent_at)

    def test_sms_aggregation_preserves_terminal_sent_at(self):
        sent_at = timezone.now() - timedelta(hours=2)
        campaign = SmsCampaign.objects.create(
            name="Stable SMS timestamp",
            message="Hello",
            status="sent",
            sent_at=sent_at,
        )
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095550101",
            status="sent",
        )

        aggregate_sms_campaign(campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "sent")
        self.assertEqual(campaign.sent_at, sent_at)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locking required")
@override_settings(BACKGROUND_JOBS_ENABLED=True)
class DeliveryRecoveryInterleavingTests(TransactionTestCase):
    def test_worker_cannot_claim_manual_retry_before_recipient_mirror_commits(self):
        sender = make_superuser()
        campaign = EmailCampaign.objects.create(
            name="Atomic manual retry",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=sender)
        log = RecipientLog.objects.get(campaign=campaign)
        job = claim_jobs()[0]
        completed_at = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk).update(
            status=BackgroundJob.Status.UNCERTAIN,
            claim_token=None,
            claimed_at=None,
            completed_at=completed_at,
        )
        RecipientLog.objects.filter(pk=log.pk).update(
            status="uncertain",
            claim_token=None,
            claimed_at=None,
            uncertain_at=completed_at,
        )
        aggregate_email_campaign(campaign.pk)
        job.refresh_from_db()

        mirror_started = threading.Event()
        release_mirror = threading.Event()
        retry_results = []
        worker_claims = []
        errors = []
        real_aggregate = aggregate_email_campaign

        def blocking_aggregate(campaign_id):
            mirror_started.set()
            if not release_mirror.wait(timeout=5):
                raise TimeoutError("test did not release recipient mirror")
            real_aggregate(campaign_id)

        def retry():
            close_old_connections()
            try:
                retry_results.append(retry_job(job))
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        def claim():
            close_old_connections()
            try:
                worker_claims.append([claimed.pk for claimed in claim_jobs()])
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        with patch(
            "apps.mail.services.campaign.dispatch.aggregate_email_campaign",
            side_effect=blocking_aggregate,
        ):
            retry_thread = threading.Thread(target=retry)
            retry_thread.start()
            self.assertTrue(mirror_started.wait(timeout=5))

            worker_thread = threading.Thread(target=claim)
            worker_thread.start()
            worker_thread.join(timeout=5)
            self.assertFalse(worker_thread.is_alive())
            release_mirror.set()
            retry_thread.join(timeout=5)

        self.assertFalse(retry_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(worker_claims, [[]])
        self.assertEqual(retry_results, [True])
        job.refresh_from_db()
        log.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(log.status, "retry")
        self.assertEqual(claim_jobs()[0].pk, job.pk)

    def test_recovery_log_lock_prevents_late_provider_success_from_splitting_state(self):
        sender = make_superuser()
        campaign = EmailCampaign.objects.create(
            name="Interleaved recovery",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=sender)
        log = RecipientLog.objects.get(campaign=campaign)
        job = claim_jobs()[0]
        stale_at = timezone.now() - timedelta(hours=1)
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            provider_call_started_at=stale_at,
        )
        RecipientLog.objects.filter(pk=log.pk).update(
            status="processing",
            claim_token=job.claim_token,
            claimed_at=stale_at,
        )

        resolver_locked = threading.Event()
        release_recovery = threading.Event()
        provider_attempted = threading.Event()
        provider_updates = []
        recovery_results = []
        errors = []

        def blocking_resolver(current_job):
            result = resolve_stale_delivery_job(current_job)
            resolver_locked.set()
            if not release_recovery.wait(timeout=5):
                raise TimeoutError("test did not release recovery")
            return result

        def recover():
            close_old_connections()
            try:
                recovery_results.append(recover_stale_jobs(stale_after=timedelta(minutes=10)))
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        def record_provider_success():
            close_old_connections()
            try:
                provider_attempted.set()
                provider_updates.append(
                    RecipientLog.objects.filter(
                        pk=log.pk,
                        status="processing",
                        claim_token=job.claim_token,
                    ).update(
                        status="sent",
                        sent_at=timezone.now(),
                        provider_message_id="late-provider-result",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        with patch(
            "apps.core.services.background_jobs.recovery.resolve_stale_job_state",
            side_effect=blocking_resolver,
        ):
            recovery_thread = threading.Thread(target=recover)
            recovery_thread.start()
            self.assertTrue(resolver_locked.wait(timeout=5))

            provider_thread = threading.Thread(target=record_provider_success)
            provider_thread.start()
            self.assertTrue(provider_attempted.wait(timeout=5))
            release_recovery.set()

            recovery_thread.join(timeout=5)
            provider_thread.join(timeout=5)

        self.assertFalse(recovery_thread.is_alive())
        self.assertFalse(provider_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(recovery_results[0]["uncertain"], 1)
        self.assertEqual(provider_updates, [0])
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(log.provider_message_id, "")
        self.assertEqual(campaign.status, "failed")
