import threading
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs.worker import claim_jobs
from apps.event.models import (
    Event,
    RegistrationSheetSyncConfig,
)
from apps.event.services.registration_sheet_sync.scheduler import (
    JOB_KIND,
    begin_sync,
    complete_sync,
    fail_sync,
    job_should_run,
    schedule_registration_sync,
)
from apps.event.tests.helpers import make_event


class _RegistrationSheetSchedulerCase(TestCase):
    def setUp(self):
        cache.clear()
        self.event = make_event()
        # Link without a signal so each test controls its first source request.
        Event.objects.filter(pk=self.event.pk).update(registration_sheet_id="test-sheet")
        self.event.refresh_from_db()

    def config(self):
        return RegistrationSheetSyncConfig.objects.get(event=self.event)

    def claim(self, job):
        BackgroundJob.objects.filter(pk=job.pk).update(available_at=timezone.now() - timedelta(seconds=1))
        return next(item for item in claim_jobs(batch_size=100) if item.pk == job.pk)


class RegistrationSheetSchedulerTest(_RegistrationSheetSchedulerCase):
    def test_unlinked_event_creates_no_configuration_or_job(self):
        event = make_event(name="Unlinked")
        self.assertIsNone(schedule_registration_sync(event))
        self.assertFalse(RegistrationSheetSyncConfig.objects.filter(event=event).exists())
        self.assertFalse(BackgroundJob.objects.filter(kind=JOB_KIND).exists())

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_requests_are_durable_even_without_in_process_worker(self):
        now = timezone.now()
        with patch("apps.event.services.registration_sheet_sync.scheduler.timezone.now", return_value=now):
            job = schedule_registration_sync(self.event)
        self.assertEqual(job.available_at, now + timedelta(seconds=15))
        self.assertEqual(self.config().requested_generation, 1)
        self.assertEqual(self.config().pending_job_id, job.pk)

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_without_worker_an_in_process_sync_starts_after_commit(self):
        with patch("apps.event.services.registration_sheet_sync.append._schedule_in_process_sync") as start:
            with self.captureOnCommitCallbacks(execute=True):
                schedule_registration_sync(self.event)
            start.assert_called_once_with(str(self.event.pk), 15.0, False)
            start.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                schedule_registration_sync(self.event, immediate=True)
            self.assertEqual(start.call_args.args[0], str(self.event.pk))
            self.assertLessEqual(start.call_args.args[1], 0)
            self.assertTrue(start.call_args.args[2])

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_with_worker_no_in_process_sync_starts(self):
        with patch("apps.event.services.registration_sheet_sync.append._schedule_in_process_sync") as start:
            with self.captureOnCommitCallbacks(execute=True):
                schedule_registration_sync(self.event)
        start.assert_not_called()

    def test_in_process_timer_runs_only_pending_work(self):
        from apps.event.services.registration_sheet_sync import append

        event_id = str(self.event.pk)
        RegistrationSheetSyncConfig.objects.create(event=self.event)
        with patch.object(append, "_flush_pending_sync") as flush, patch.object(append, "close_old_connections"):
            append._sync_timers[event_id] = threading.current_thread()
            append._run_in_process_sync(event_id, False)
            flush.assert_not_called()
            schedule_registration_sync(self.event)
            append._sync_timers[event_id] = threading.current_thread()
            append._run_in_process_sync(event_id, False)
            flush.assert_called_once_with(event_id, immediate=False)
            # A replaced timer does nothing.
            append._run_in_process_sync(event_id, False)
            flush.assert_called_once()

    def test_failed_explicit_sync_keeps_queued_changes(self):
        job = schedule_registration_sync(self.event)
        captured = begin_sync(self.event.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.PENDING)
        self.assertEqual(self.config().pending_job_id, job.pk)
        fail_sync(self.event.pk, captured["captured_generation"], "Google returned 503")
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.PENDING)
        self.assertEqual(self.config().pending_job_id, job.pk)
        self.assertTrue(job_should_run(job))

    def test_successful_explicit_sync_cancels_queued_job(self):
        job = schedule_registration_sync(self.event)
        captured = begin_sync(self.event.pk)
        complete_sync(self.event.pk, captured["captured_generation"])
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.CANCELLED)
        self.assertIsNone(self.config().pending_job_id)
        self.assertEqual(self.config().state, "succeeded")

    def test_burst_coalesces_and_capped_debounce_never_starves(self):
        start = timezone.now()
        for seconds in (0, 10, 20, 40, 55, 59):
            now = start + timedelta(seconds=seconds)
            with patch("apps.event.services.registration_sheet_sync.scheduler.timezone.now", return_value=now):
                job = schedule_registration_sync(self.event)
        self.assertEqual(BackgroundJob.objects.filter(kind=JOB_KIND).count(), 1)
        self.assertEqual(job.available_at, start + timedelta(seconds=60))
        self.assertEqual(self.config().requested_generation, 6)

    def test_interval_has_fixed_boundary_anchored_to_last_success(self):
        start = timezone.now()
        RegistrationSheetSyncConfig.objects.create(event=self.event, sync_mode="interval", last_success_at=start)
        with patch(
            "apps.event.services.registration_sheet_sync.scheduler.timezone.now",
            return_value=start + timedelta(seconds=20),
        ):
            first = schedule_registration_sync(self.event)
        with patch(
            "apps.event.services.registration_sheet_sync.scheduler.timezone.now",
            return_value=start + timedelta(minutes=4),
        ):
            second = schedule_registration_sync(self.event)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.available_at, start + timedelta(minutes=5))

    def test_manual_changes_remain_dirty_until_explicit_request(self):
        RegistrationSheetSyncConfig.objects.create(event=self.event, sync_mode="manual")
        self.assertIsNone(schedule_registration_sync(self.event))
        self.assertEqual(self.config().requested_generation, 1)
        job = schedule_registration_sync(self.event, immediate=True)
        self.assertEqual(job.payload["immediate"], True)
        self.assertLessEqual(job.available_at, timezone.now())
        self.assertTrue(job_should_run(job))

    def test_automatic_change_does_not_postpone_manual_sync_now(self):
        start = timezone.now()
        with patch("apps.event.services.registration_sheet_sync.scheduler.timezone.now", return_value=start):
            first = schedule_registration_sync(self.event, immediate=True)
        with patch(
            "apps.event.services.registration_sheet_sync.scheduler.timezone.now",
            return_value=start + timedelta(seconds=1),
        ):
            second = schedule_registration_sync(self.event)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.available_at, start)

    def test_changes_during_running_job_get_followup_and_are_not_acknowledged_early(self):
        job = self.claim(schedule_registration_sync(self.event))
        captured = begin_sync(self.event.pk, job=job)
        followup = schedule_registration_sync(self.event)
        self.assertNotEqual(followup.pk, job.pk)
        complete_sync(self.event.pk, captured["captured_generation"], added=1)
        config = self.config()
        self.assertEqual(config.completed_generation, 1)
        self.assertEqual(config.requested_generation, 2)
        self.assertEqual(config.pending_job_id, followup.pk)
        self.assertEqual(config.state, "scheduled")
        next_capture = begin_sync(self.event.pk, job=self.claim(followup))
        complete_sync(self.event.pk, next_capture["captured_generation"], updated=1, unchanged=2)
        self.assertEqual(self.config().completed_generation, 2)
        self.assertEqual(self.config().last_unchanged_count, 2)
        self.assertEqual(self.config().state, "succeeded")
