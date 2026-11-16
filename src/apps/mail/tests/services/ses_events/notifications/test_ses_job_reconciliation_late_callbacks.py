from unittest.mock import patch

from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.core.services.background_jobs.metrics import worker_metrics
from apps.core.services.email import DeliveryResult
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign import dispatch
from apps.mail.services.email_monitoring.ses_events import process_sns_envelope
from apps.mail.tests.services.ses_events.notifications.test_ses_job_reconciliation import _SesJobReconciliationCase


class SesJobReconciliationTests(_SesJobReconciliationCase):
    def test_later_bounce_does_not_change_successful_submission_job(self):
        campaign, log = self.queued_campaign()
        job = claim_jobs(batch_size=1)[0]
        message_id = f"ses-{log.pk}"

        def accepted(_message, *, before_provider_call, **_kwargs):
            before_provider_call()
            return DeliveryResult(provider="ses", message_id=message_id)

        with patch("apps.mail.services.campaign.send.transport.deliver_email", side_effect=accepted):
            self.assertTrue(process_claimed_job(job))
        job.refresh_from_db()
        completed_at = job.completed_at
        updated_at = job.updated_at
        log.refresh_from_db()

        process_sns_envelope(self.callback(log, event_type="Bounce", message_id=message_id))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(log.status, "bounced")
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(job.completed_at, completed_at)
        self.assertEqual(job.updated_at, updated_at)

    def test_callback_does_not_finalize_pending_unclaimed_job(self):
        campaign, log = self.queued_campaign()
        job = BackgroundJob.objects.get(payload__recipient_log_id=str(log.pk))
        log.provider = "ses"
        log.provider_message_id = f"ses-{log.pk}"
        log.save(update_fields=["provider", "provider_message_id"])

        process_sns_envelope(self.callback(log))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.PENDING)
        self.assertEqual(job.attempts, 0)
        self.assertIsNone(job.completed_at)

    def test_duplicate_callback_reconciles_existing_confirmed_recipient(self):
        campaign, log, job = self.uncertain_delivery()
        envelope = self.callback(log)
        # Recreate the state left by callbacks handled before reconciliation
        # existed: the recipient was confirmed but the job remained uncertain.
        log.provider = "ses"
        log.provider_message_id = f"ses-{log.pk}"
        log.status = "delivered"
        log.sent_at = timezone.now()
        log.delivered_at = timezone.now()
        log.last_sns_message_id = envelope["MessageId"]
        log.uncertain_at = None
        log.error_message = ""
        log.save()
        dispatch.aggregate_email_campaign(campaign.pk)

        process_sns_envelope(envelope)

        self.assert_confirmed(campaign, log, job)

    def test_duplicate_failure_callback_preserves_completion_and_update_times(self):
        campaign, log, job = self.uncertain_delivery()
        envelope = self.callback(log, event_type="Bounce")
        process_sns_envelope(envelope)
        self.assert_confirmed(campaign, log, job, log_status="bounced", success=False)
        completed_at = job.completed_at
        job_updated_at = job.updated_at
        log_updated_at = log.updated_at

        process_sns_envelope(envelope)

        job.refresh_from_db()
        log.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(job.completed_at, completed_at)
        self.assertEqual(job.updated_at, job_updated_at)
        self.assertEqual(log.updated_at, log_updated_at)

    def test_aggregation_failure_rolls_back_confirmation_before_callback_retry(self):
        campaign, log, job = self.uncertain_delivery()
        envelope = self.callback(log)
        before_job = BackgroundJob.objects.values().get(pk=job.pk)
        before_log = RecipientLog.objects.values().get(pk=log.pk)
        before_campaign = EmailCampaign.objects.values().get(pk=campaign.pk)

        with (
            patch(
                "apps.mail.services.campaign.dispatch.aggregate_email_campaign",
                side_effect=RuntimeError("Campaign aggregation failed."),
            ),
            self.assertRaisesRegex(RuntimeError, "Campaign aggregation failed"),
        ):
            process_sns_envelope(envelope)

        self.assertEqual(BackgroundJob.objects.values().get(pk=job.pk), before_job)
        self.assertEqual(RecipientLog.objects.values().get(pk=log.pk), before_log)
        self.assertEqual(EmailCampaign.objects.values().get(pk=campaign.pk), before_campaign)
        self.assertEqual(worker_metrics()["uncertain_jobs"], 1)

        process_sns_envelope(envelope)

        self.assert_confirmed(campaign, log, job)
