from datetime import timedelta
from unittest.mock import Mock, patch

from botocore.exceptions import ReadTimeoutError
from django.db import OperationalError
from django.test import TestCase, override_settings
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
from apps.mail.services.background_jobs import (
    _send_via_sms,
    aggregate_email_campaign,
    queue_email_campaign,
    queue_sms_campaign,
)
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

    @patch("apps.mail.services.background_jobs._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.background_jobs._recipient_context", return_value={})
    @patch(
        "apps.mail.services.background_jobs._send_via_ses",
        return_value=SesSendResult(message_id="ses-123"),
    )
    @patch("apps.mail.services.background_jobs._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.background_jobs.EmailServiceConfig.load")
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
        self.assertEqual(log.ses_message_id, "ses-123")
        self.assertEqual(campaign.status, "sent")
        self.assertEqual(campaign.sent_count, 1)

    @patch("apps.mail.services.background_jobs.wait_for_delivery_slot")
    @patch("apps.mail.services.background_jobs._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.background_jobs._recipient_context", return_value={})
    @patch(
        "apps.mail.services.background_jobs._send_via_ses",
        return_value=SesSendResult(message_id="ses-rate"),
    )
    @patch("apps.mail.services.background_jobs._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.background_jobs.EmailServiceConfig.load")
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
            ses_configuration_set_name="",
            ses_max_send_rate=7,
        )
        self._queued_email()

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        wait_for_slot.assert_called_once_with("ses", 7.0)

    @patch(
        "apps.mail.services.background_jobs._get_ses_client",
        side_effect=OperationalError("database temporarily unavailable"),
    )
    @patch("apps.mail.services.background_jobs.EmailServiceConfig.load", return_value=Mock())
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

    @patch("apps.mail.services.background_jobs._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.background_jobs._recipient_context", return_value={})
    @patch(
        "apps.mail.services.background_jobs._send_via_ses",
        return_value=SesSendResult(error="timeout"),
    )
    @patch("apps.mail.services.background_jobs._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.background_jobs.EmailServiceConfig.load")
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

    @patch("apps.mail.services.background_jobs._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.background_jobs._recipient_context", return_value={})
    @patch(
        "apps.mail.services.background_jobs._send_via_ses",
        return_value=SesSendResult(
            error="SES temporarily rejected the request.",
            outcome=SES_OUTCOME_TRANSIENT,
        ),
    )
    @patch("apps.mail.services.background_jobs._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.background_jobs.EmailServiceConfig.load")
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

    @patch("apps.mail.services.background_jobs._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.background_jobs._recipient_context", return_value={})
    @patch(
        "apps.mail.services.background_jobs._send_via_ses",
        return_value=SesSendResult(
            error="SES rejected the request.",
            outcome=SES_OUTCOME_PERMANENT,
        ),
    )
    @patch("apps.mail.services.background_jobs._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.background_jobs.EmailServiceConfig.load")
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
        "apps.mail.services.background_jobs._send_via_sms",
        side_effect=_provider_failure(PhoneVerificationThrottled("slow down")),
    )
    @patch(
        "apps.mail.services.background_jobs.AWSCredentialConfig.load",
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
        "apps.mail.services.background_jobs._send_via_sms",
        side_effect=_provider_failure(PhoneVerificationInvalid("invalid phone")),
    )
    @patch(
        "apps.mail.services.background_jobs.AWSCredentialConfig.load",
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
        "apps.mail.services.background_jobs._send_via_sms",
        side_effect=_provider_failure(ReadTimeoutError(endpoint_url="https://sms-voice.us-west-2.amazonaws.com")),
    )
    @patch(
        "apps.mail.services.background_jobs.AWSCredentialConfig.load",
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

    @patch("apps.mail.services.background_jobs.boto3.client")
    @patch("apps.mail.services.background_jobs.resolve_aws_credentials")
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
            ses_message_id="known-provider-id",
        )
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            provider_call_started_at=stale_at,
        )

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        log.refresh_from_db()
        self.assertEqual(result["completed"], 1)
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(log.status, "sent")

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
