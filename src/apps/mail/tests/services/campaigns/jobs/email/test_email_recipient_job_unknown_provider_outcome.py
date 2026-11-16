from unittest.mock import Mock, patch

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

from ..durable_queue_helpers import DurableCampaignQueueTestCase


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class EmailRecipientJobTests(DurableCampaignQueueTestCase):
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
