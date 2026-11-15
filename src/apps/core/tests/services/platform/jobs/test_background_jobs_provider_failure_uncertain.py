from datetime import timedelta
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    PermanentJobError,
    TransientJobError,
    claim_jobs,
    enqueue_job,
    process_claimed_job,
    recover_stale_jobs,
    retry_job,
)


class BackgroundJobQueueTests(TestCase):
    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_provider_failure_is_uncertain_and_not_automatically_retried(self, get_handler):
        def fail(job):
            job.begin_provider_call()
            raise TimeoutError("provider timeout")

        get_handler.return_value = fail
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="uncertain",
            payload={},
            can_retry_after_claim=False,
        )
        claimed = claim_jobs()[0]

        self.assertFalse(process_claimed_job(claimed))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertIsNotNone(job.completed_at)
        self.assertTrue(retry_job(job))
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)

    @patch(
        "apps.core.services.background_jobs.registry.notify_job_state",
        side_effect=OperationalError("domain mirror unavailable"),
    )
    def test_manual_retry_rolls_back_if_domain_mirror_fails(self, _notify):
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="atomic-manual-retry",
            payload={},
        )
        completed_at = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk).update(
            status=BackgroundJob.Status.UNCERTAIN,
            completed_at=completed_at,
            last_error="Review delivery",
        )
        job.refresh_from_db()

        with self.assertRaisesMessage(OperationalError, "domain mirror unavailable"):
            retry_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(job.completed_at, completed_at)
        self.assertEqual(job.last_error, "Review delivery")
        self.assertEqual(claim_jobs(), [])

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_definitive_transient_provider_rejection_retries_after_call_started(self, get_handler):
        def fail(job):
            job.begin_provider_call()
            raise TransientJobError("provider throttled")

        get_handler.return_value = fail
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="definitive-transient",
            payload={},
            can_retry_after_claim=False,
        )

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_definitive_permanent_provider_rejection_fails_not_uncertain(self, get_handler):
        def fail(job):
            job.begin_provider_call()
            raise PermanentJobError("access denied")

        get_handler.return_value = fail
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="definitive-permanent",
            payload={},
            can_retry_after_claim=False,
        )

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)

    def test_stale_recovery_retries_safe_jobs_and_quarantines_deliveries(self):
        stale_at = timezone.now() - timedelta(hours=1)
        safe, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="safe",
            payload={},
            can_retry_after_claim=True,
        )
        delivery, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="delivery",
            payload={},
            can_retry_after_claim=False,
        )
        BackgroundJob.objects.filter(pk=safe.pk).update(
            status=BackgroundJob.Status.PROCESSING,
            claimed_at=stale_at,
            claim_token=BackgroundJob.new_claim_token(),
        )
        BackgroundJob.objects.filter(pk=delivery.pk).update(
            status=BackgroundJob.Status.PROCESSING,
            claimed_at=stale_at,
            claim_token=BackgroundJob.new_claim_token(),
            provider_call_started_at=stale_at,
        )

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        self.assertEqual(result, {"completed": 0, "retried": 1, "failed": 0, "uncertain": 1})
        safe.refresh_from_db()
        delivery.refresh_from_db()
        self.assertEqual(safe.status, BackgroundJob.Status.RETRY)
        self.assertEqual(delivery.status, BackgroundJob.Status.UNCERTAIN)

    def test_stale_recovery_fails_job_at_max_attempts(self):
        stale_at = timezone.now() - timedelta(hours=1)
        job, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="exhausted-stale-job",
            payload={},
            max_attempts=1,
        )
        claimed = claim_jobs()[0]
        BackgroundJob.objects.filter(pk=claimed.pk).update(claimed_at=stale_at)

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        self.assertEqual(result, {"completed": 0, "retried": 0, "failed": 1, "uncertain": 0})
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertIsNotNone(job.completed_at)
        self.assertIn("Maximum attempts", job.last_error)
        self.assertEqual(claim_jobs(), [])
