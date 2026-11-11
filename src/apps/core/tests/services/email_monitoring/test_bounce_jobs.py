"""The bounce scans in the background worker: scheduling, the chain of scans, timing, and their own retention."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, run_claimed_job
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND, ScanOutcome, ensure_scheduled, run_now
from apps.core.services.email.bounces.jobs import next_delay, purge_finished_jobs, run_scan_job

from .helpers import monitoring_settings

SCAN = "apps.core.services.email.bounces.scanner.scan_mailbox"
CONSUMERS = "apps.core.services.email.bounces.jobs.active_consumer_kinds"
NOTIFY = "apps.core.services.email.bounces.jobs.notify_consumers"


def no_inbound_consumer():
    """Bounce processing alone: no app consumes inbound mail (the interval stays the bounce interval)."""
    return patch(CONSUMERS, return_value=[])


def scan_jobs():
    return BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND)


class SchedulingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_maintenance_queues_one_scan_and_no_second_while_it_waits(self):
        self.assertTrue(ensure_scheduled())
        self.assertFalse(ensure_scheduled())

        job = scan_jobs().get()
        self.assertEqual((job.status, job.max_attempts), (BackgroundJob.Status.PENDING, 1))

    @monitoring_settings(bounce_processing_enabled=False)
    def test_switched_off_nothing_is_queued(self):
        self.assertFalse(ensure_scheduled())
        self.assertFalse(run_now())
        self.assertFalse(scan_jobs().exists())

    def test_scan_now_queues_an_immediate_scan_even_when_one_is_scheduled(self):
        ensure_scheduled(now=timezone.now() + timedelta(minutes=10))

        self.assertTrue(run_now())

        self.assertEqual(scan_jobs().filter(available_at__lte=timezone.now()).count(), 1)

    def test_a_scan_queues_the_next_one_after_the_interval(self):
        with (
            patch(SCAN, return_value=ScanOutcome("ok")),
            monitoring_settings(bounce_scan_interval_seconds=600),
            no_inbound_consumer(),
        ):
            run_scan_job(job=None)

        job = scan_jobs().get()
        self.assertAlmostEqual((job.available_at - timezone.now()).total_seconds(), 600, delta=5)

    def test_while_an_inbound_consumer_is_on_scans_come_every_inbox_interval(self):
        settings = monitoring_settings(bounce_scan_interval_seconds=600, inbox_scan_interval_seconds=120)
        with patch(SCAN, return_value=ScanOutcome("ok")), settings, patch(CONSUMERS, return_value=["app.ingest"]):
            run_scan_job(job=None)
            self.assertEqual(next_delay(ScanOutcome("ok")), 120)

        job = scan_jobs().get()
        self.assertAlmostEqual((job.available_at - timezone.now()).total_seconds(), 120, delta=5)

    def test_the_interval_never_goes_below_a_minute(self):
        settings = monitoring_settings(bounce_scan_interval_seconds=600, inbox_scan_interval_seconds=5)
        with settings, patch(CONSUMERS, return_value=["app.ingest"]):
            self.assertEqual(next_delay(None), 60)

    def test_a_scan_that_recorded_inbound_mail_wakes_the_consumers(self):
        recorded = ScanOutcome("ok", stats={"recorded": 2})
        with patch(SCAN, return_value=recorded), patch(NOTIFY) as notify:
            run_scan_job(job=None)
        notify.assert_called_once_with()

        with patch(SCAN, return_value=ScanOutcome("ok", stats={"recorded": 0})), patch(NOTIFY) as notify:
            run_scan_job(job=None)
        notify.assert_not_called()

    def test_a_scan_that_fails_unexpectedly_still_queues_the_next(self):
        with patch(SCAN, side_effect=RuntimeError("database gone")), self.assertRaises(RuntimeError):
            run_scan_job(job=None)

        self.assertEqual(scan_jobs().count(), 1)

    def test_no_successor_is_queued_while_another_scan_waits(self):
        run_now()

        with patch(SCAN, return_value=ScanOutcome("ok")):
            run_scan_job(job=None)

        self.assertEqual(scan_jobs().count(), 1)

    def test_the_next_scan_waits_longer_when_microsoft_asks_and_comes_sooner_to_catch_up(self):
        with monitoring_settings(bounce_scan_interval_seconds=600), no_inbound_consumer():
            self.assertEqual(next_delay(None), 600)
            self.assertEqual(next_delay(ScanOutcome("ok")), 600)
            self.assertEqual(next_delay(ScanOutcome("busy", retry_after=1800)), 1800)
            self.assertEqual(next_delay(ScanOutcome("busy", retry_after=30)), 600)
            self.assertEqual(next_delay(ScanOutcome("partial")), 120)

    def test_the_worker_runs_a_scan_job_through_its_registered_handler(self):
        run_now()

        with patch(SCAN, return_value=ScanOutcome("ok")) as scan:
            for job in claim_jobs():
                run_claimed_job(job)

        scan.assert_called_once_with()
        self.assertEqual(scan_jobs().filter(status=BackgroundJob.Status.SUCCEEDED).count(), 1)
        self.assertEqual(scan_jobs().filter(status=BackgroundJob.Status.PENDING).count(), 1)

    def test_finished_scan_jobs_older_than_a_week_are_purged(self):
        old, recent = timezone.now() - timedelta(days=8), timezone.now() - timedelta(days=1)
        for completed in (old, recent):
            BackgroundJob.objects.create(
                kind=BOUNCE_SCAN_JOB_KIND, dedupe_key=str(completed), status="succeeded", completed_at=completed
            )
        BackgroundJob.objects.create(kind="other.kind", dedupe_key="x", status="succeeded", completed_at=old)

        self.assertEqual(purge_finished_jobs(), 1)
        self.assertEqual(scan_jobs().count(), 1)
        self.assertTrue(BackgroundJob.objects.filter(kind="other.kind").exists())
