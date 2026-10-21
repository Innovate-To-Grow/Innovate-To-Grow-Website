"""One email recipient's durable job: provider outcomes, rate limiting and retry classification."""

from unittest.mock import Mock, patch

from django.db import OperationalError
from django.test import override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    claim_jobs,
    process_claimed_job,
)
from apps.mail.models import RecipientLog
from apps.mail.services.send_campaign import SesSendResult
from apps.mail.services.send_campaign.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_TRANSIENT,
)

from .durable_queue_helpers import DurableCampaignQueueTestCase


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class EmailRecipientJobTests(DurableCampaignQueueTestCase):
    """One email recipient's durable job: provider outcomes, rate limiting and retry classification."""

    @patch("apps.mail.services.campaign.dispatch.email_job._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch.email_job._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch.email_job._send_via_ses",
        return_value=SesSendResult(message_id="ses-123"),
    )
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load")
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

    @patch("apps.mail.services.campaign.dispatch.email_job._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch.email_job._recipient_context", return_value={})
    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses")
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load")
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

    @patch("apps.mail.services.campaign.dispatch.email_job.wait_for_delivery_slot")
    @patch("apps.mail.services.campaign.dispatch.email_job._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch.email_job._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch.email_job._send_via_ses",
        return_value=SesSendResult(message_id="ses-rate"),
    )
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load")
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
        "apps.mail.services.campaign.dispatch.email_job._get_ses_client",
        side_effect=OperationalError("database temporarily unavailable"),
    )
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load", return_value=Mock())
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

    @patch("apps.mail.services.campaign.dispatch.email_job._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch.email_job._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch.email_job._send_via_ses",
        return_value=SesSendResult(error="timeout"),
    )
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load")
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

    @patch("apps.mail.services.campaign.dispatch.email_job._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch.email_job._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch.email_job._send_via_ses",
        return_value=SesSendResult(
            error="SES temporarily rejected the request.",
            outcome=SES_OUTCOME_TRANSIENT,
        ),
    )
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load")
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

    @patch("apps.mail.services.campaign.dispatch.email_job._unsubscribe_url_for", return_value="")
    @patch("apps.mail.services.campaign.dispatch.email_job._recipient_context", return_value={})
    @patch(
        "apps.mail.services.campaign.dispatch.email_job._send_via_ses",
        return_value=SesSendResult(
            error="SES rejected the request.",
            outcome=SES_OUTCOME_PERMANENT,
        ),
    )
    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load")
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

    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses")
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
