from datetime import timedelta
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    enqueue_job,
    recover_stale_jobs,
    worker_metrics,
)


class BackgroundJobQueueTests(TestCase):
    def test_recovery_mirror_failure_rolls_back_one_job_without_blocking_next(self):
        stale_at = timezone.now() - timedelta(hours=1)
        broken, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="broken-recovery-mirror",
            payload={},
        )
        healthy, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="healthy-recovery-mirror",
            payload={},
        )
        BackgroundJob.objects.filter(pk__in=[broken.pk, healthy.pk]).update(
            status=BackgroundJob.Status.PROCESSING,
            claimed_at=stale_at,
            claim_token=BackgroundJob.new_claim_token(),
        )

        def mirror(job):
            if job.pk == broken.pk:
                raise OperationalError("mirror database unavailable")

        with patch(
            "apps.core.services.background_jobs.recovery.notify_job_state",
            side_effect=mirror,
        ):
            result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        broken.refresh_from_db()
        healthy.refresh_from_db()
        self.assertEqual(result, {"completed": 0, "retried": 1, "failed": 0, "uncertain": 0})
        self.assertEqual(broken.status, BackgroundJob.Status.PROCESSING)
        self.assertIsNotNone(broken.claim_token)
        self.assertEqual(healthy.status, BackgroundJob.Status.RETRY)
        self.assertIsNone(healthy.claim_token)

    def test_metrics_report_queue_and_terminal_counts(self):
        enqueue_job(kind="test.echo", dedupe_key="pending", payload={})
        failed, _created = enqueue_job(kind="test.echo", dedupe_key="failed", payload={})
        uncertain, _created = enqueue_job(kind="test.echo", dedupe_key="uncertain-metric", payload={})
        BackgroundJob.objects.filter(pk=failed.pk).update(status=BackgroundJob.Status.FAILED)
        BackgroundJob.objects.filter(pk=uncertain.pk).update(status=BackgroundJob.Status.UNCERTAIN)

        metrics = worker_metrics()

        self.assertEqual(metrics["heartbeat"], 1)
        self.assertEqual(metrics["queue_depth"], 1)
        self.assertEqual(metrics["failed_jobs"], 1)
        self.assertEqual(metrics["uncertain_jobs"], 1)
