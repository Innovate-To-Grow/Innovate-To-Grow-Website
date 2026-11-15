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
from apps.mail.models import RecipientLog

from ..jobs.durable_queue_helpers import DurableCampaignQueueTestCase


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
