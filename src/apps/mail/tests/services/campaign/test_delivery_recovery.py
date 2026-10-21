"""Recovering stale delivery claims, manual retries, and claim fencing between workers."""

from datetime import timedelta
from unittest.mock import patch

from django.db import OperationalError
from django.test import override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    claim_jobs,
    recover_stale_jobs,
    retry_job,
)
from apps.mail.models import RecipientLog, SmsRecipientLog
from apps.mail.services.campaign.dispatch import (
    aggregate_email_campaign,
    aggregate_sms_campaign,
    sync_delivery_job_state,
)
from apps.mail.services.campaign.dispatch.channels import EMAIL, SMS, mark_log_processing

from .durable_queue_helpers import DurableCampaignQueueTestCase


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class DeliveryRecoveryTests(DurableCampaignQueueTestCase):
    """Recovering stale delivery claims, manual retries, and claim fencing between workers."""

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
            "apps.mail.services.campaign.dispatch.job_state.aggregate_email_campaign",
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
                "apps.mail.services.campaign.dispatch.job_state.aggregate_email_campaign",
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

        self.assertFalse(mark_log_processing(EMAIL, log, stale_job))

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

        self.assertFalse(mark_log_processing(SMS, log, stale_job))

        log.refresh_from_db()
        self.assertEqual(log.status, "pending")
        self.assertIsNone(log.claim_token)
