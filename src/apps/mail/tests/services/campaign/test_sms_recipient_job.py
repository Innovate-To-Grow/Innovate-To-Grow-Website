"""One SMS recipient's durable job: provider outcomes and retry classification."""

from unittest.mock import Mock, patch

from botocore.exceptions import ReadTimeoutError
from django.test import override_settings

from apps.authn.services.sms import PhoneVerificationInvalid, PhoneVerificationThrottled
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    claim_jobs,
    process_claimed_job,
)
from apps.mail.models import SmsRecipientLog
from apps.mail.services.campaign.dispatch.sms_job import _send_via_sms

from .durable_queue_helpers import DurableCampaignQueueTestCase, _provider_failure


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class SmsRecipientJobTests(DurableCampaignQueueTestCase):
    """One SMS recipient's durable job: provider outcomes and retry classification."""

    @patch(
        "apps.mail.services.campaign.dispatch.sms_job._send_via_sms",
        side_effect=_provider_failure(PhoneVerificationThrottled("slow down")),
    )
    @patch(
        "apps.mail.services.campaign.dispatch.sms_job.AWSCredentialConfig.load",
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
        "apps.mail.services.campaign.dispatch.sms_job._send_via_sms",
        side_effect=_provider_failure(PhoneVerificationInvalid("invalid phone")),
    )
    @patch(
        "apps.mail.services.campaign.dispatch.sms_job.AWSCredentialConfig.load",
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
        "apps.mail.services.campaign.dispatch.sms_job._send_via_sms",
        side_effect=_provider_failure(ReadTimeoutError(endpoint_url="https://sms-voice.us-west-2.amazonaws.com")),
    )
    @patch(
        "apps.mail.services.campaign.dispatch.sms_job.AWSCredentialConfig.load",
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

    @patch("apps.mail.services.campaign.dispatch.sms_job._send_via_sms")
    @patch(
        "apps.mail.services.campaign.dispatch.sms_job.AWSCredentialConfig.load",
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

    @patch("apps.mail.services.campaign.dispatch.sms_job.boto3.client")
    @patch("apps.mail.services.campaign.dispatch.sms_job.resolve_aws_credentials")
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
