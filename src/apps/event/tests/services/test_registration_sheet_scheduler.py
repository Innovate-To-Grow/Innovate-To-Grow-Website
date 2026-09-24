import threading
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs.worker import claim_jobs
from apps.event.models import (
    Event,
    EventRegistration,
    Question,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncRecord,
)
from apps.event.services.registration_sheet_sync.scheduler import (
    JOB_KIND,
    begin_sync,
    complete_sync,
    fail_sync,
    job_should_run,
    mirror_job_state,
    schedule_registration_sync,
)
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket


class RegistrationSheetSchedulerTest(TestCase):
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

    def test_covered_queued_followup_is_cancelled(self):
        first = self.claim(schedule_registration_sync(self.event))
        followup = schedule_registration_sync(self.event)
        captured = begin_sync(self.event.pk, job=first)
        complete_sync(self.event.pk, captured["captured_generation"])
        followup.refresh_from_db()
        self.assertEqual(followup.status, BackgroundJob.Status.CANCELLED)
        self.assertFalse(job_should_run(first))

    def test_failed_same_generation_cannot_overwrite_success(self):
        schedule_registration_sync(self.event)
        first = begin_sync(self.event.pk)
        second = begin_sync(self.event.pk)
        self.assertEqual(first["captured_generation"], second["captured_generation"])
        complete_sync(self.event.pk, first["captured_generation"], added=2)
        fail_sync(self.event.pk, second["captured_generation"], "Late error", blocked=True)
        self.assertEqual(self.config().state, "succeeded")
        self.assertEqual(self.config().last_error, "")

    def test_blocked_sync_preserves_dirty_state_and_waits_for_manual_review(self):
        job = self.claim(schedule_registration_sync(self.event))
        captured = begin_sync(self.event.pk, job=job)
        fail_sync(self.event.pk, captured["captured_generation"], "Conflicting headers", blocked=True, conflicts=1)
        self.assertIsNone(schedule_registration_sync(self.event))
        self.assertEqual(self.config().completed_generation, 0)
        self.assertEqual(self.config().state, "blocked")
        self.assertEqual(self.config().last_conflict_count, 1)
        self.assertIsNotNone(schedule_registration_sync(self.event, immediate=True))

    def test_worker_retry_is_reflected_in_status(self):
        job = self.claim(schedule_registration_sync(self.event))
        captured = begin_sync(self.event.pk, job=job)
        fail_sync(self.event.pk, captured["captured_generation"], "Temporary failure")
        job.status = BackgroundJob.Status.RETRY
        job.available_at = timezone.now() + timedelta(seconds=30)
        job.last_error = "Temporary failure"
        mirror_job_state(job)
        self.assertEqual(self.config().next_sync_at, job.available_at)
        self.assertEqual(self.config().state, "scheduled")

    def test_source_transaction_rollback_removes_dirty_state_and_job(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.event.name = "Rolled back"
            self.event.save()
            self.assertTrue(BackgroundJob.objects.filter(kind=JOB_KIND).exists())
            raise RuntimeError("Rollback")
        self.assertFalse(BackgroundJob.objects.filter(kind=JOB_KIND).exists())
        self.assertFalse(RegistrationSheetSyncConfig.objects.filter(event=self.event).exists())
        self.event.refresh_from_db()
        self.assertNotEqual(self.event.name, "Rolled back")

    def test_event_audit_fields_do_not_trigger_sync_loop(self):
        self.event.registration_sheet_sync_error = "Failure"
        self.event.save(update_fields=["registration_sheet_sync_error", "updated_at"])
        self.assertFalse(BackgroundJob.objects.filter(kind=JOB_KIND).exists())

    def test_registration_question_and_ticket_changes_schedule_sync(self):
        member = make_member()
        ticket = make_ticket(self.event)
        registration = make_registration(member, self.event, ticket)
        before = self.config().requested_generation
        registration.attendee_first_name = "Changed"
        registration.save()
        question = Question.objects.create(event=self.event, text="New question")
        ticket.name = "Renamed"
        ticket.save(update_fields=["name", "updated_at"])
        question.delete()
        self.assertEqual(self.config().requested_generation, before + 4)
        registration.ticket_email_error = "Email failed"
        registration.save(update_fields=["ticket_email_error", "updated_at"])
        self.assertEqual(self.config().requested_generation, before + 4)

    def test_queryset_delete_creates_receipt_tombstone_and_survives_registration(self):
        member = make_member()
        ticket = make_ticket(self.event)
        registration = make_registration(member, self.event, ticket)
        synced_at = timezone.now()
        record = RegistrationSheetSyncRecord.objects.create(
            event=self.event, registration_id=registration.pk, synced_at=synced_at
        )
        EventRegistration.objects.filter(pk=registration.pk).delete()
        record.refresh_from_db()
        self.assertEqual(record.synced_at, synced_at)
        self.assertIsNotNone(record.deleted_at)

    def test_never_synced_delete_tombstone_is_not_a_synced_receipt(self):
        registration = make_registration(make_member(), self.event, make_ticket(self.event))
        registration_id = registration.pk
        registration.delete()
        record = RegistrationSheetSyncRecord.objects.get(registration_id=registration_id)
        self.assertIsNone(record.synced_at)
        self.assertIsNotNone(record.deleted_at)

    def test_deleting_event_does_not_recreate_configs_or_tombstones(self):
        make_ticket(self.event)
        Question.objects.create(event=self.event, text="Cascade deletion")
        event_id = self.event.pk
        Event.objects.filter(pk=event_id).delete()
        self.assertFalse(RegistrationSheetSyncConfig.objects.filter(event_id=event_id).exists())
        self.assertFalse(RegistrationSheetSyncRecord.objects.filter(event_id=event_id).exists())

    def test_disconnect_cancels_pending_work(self):
        job = schedule_registration_sync(self.event)
        self.event.registration_sheet_id = ""
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.CANCELLED)
        self.assertFalse(job_should_run(job))

    def test_mode_switch_to_manual_cancels_queued_automatic_work(self):
        job = schedule_registration_sync(self.event)
        RegistrationSheetSyncConfig.objects.filter(event=self.event).update(sync_mode="manual")
        schedule_registration_sync(self.event)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.CANCELLED)
        self.assertFalse(job_should_run(job))

    def test_invalid_settings_raise_validation_error(self):
        for fields in (
            {"debounce_seconds": 60, "max_delay_seconds": 15},
            {"field_settings": {"email": {"enabled": "yes"}}},
            {"column_mappings": {"email": 18279}},
            {"column_mappings": {"email": 2, "phone": 2}},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                RegistrationSheetSyncConfig(event=self.event, **fields).full_clean()


class RegistrationSheetSchedulerConcurrencyTest(TransactionTestCase):
    def setUp(self):
        cache.clear()
        if connection.vendor != "postgresql":
            self.skipTest("Real row-lock behavior requires PostgreSQL.")
        self.event = make_event()
        Event.objects.filter(pk=self.event.pk).update(registration_sheet_id="concurrency-sheet")
        self.event.refresh_from_db()

    def schedule_in_worker(self):
        from django.db import close_old_connections

        close_old_connections()
        try:
            schedule_registration_sync(self.event)
        finally:
            connection.close()

    def test_concurrent_first_requests_share_one_configuration_and_one_job(self):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.schedule_in_worker(), range(12)))
        config = RegistrationSheetSyncConfig.objects.get(event=self.event)
        self.assertEqual(config.requested_generation, 12)
        self.assertEqual(BackgroundJob.objects.filter(kind=JOB_KIND).count(), 1)

    def test_provider_event_lock_does_not_block_source_scheduling(self):
        from concurrent.futures import ThreadPoolExecutor

        RegistrationSheetSyncConfig.objects.create(event=self.event)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Event.objects.select_for_update(no_key=True).get(pk=self.event.pk)
                result = pool.submit(self.schedule_in_worker)
                result.result(timeout=5)
        self.assertEqual(RegistrationSheetSyncConfig.objects.get(event=self.event).requested_generation, 1)
