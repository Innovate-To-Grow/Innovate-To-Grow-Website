from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.event.models import (
    Event,
    EventRegistration,
    Question,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncRecord,
)
from apps.event.services.registration_sheet_sync.schedule.batching import schedule_registration_sync
from apps.event.services.registration_sheet_sync.schedule.state import (
    JOB_KIND,
    begin_sync,
    complete_sync,
    fail_sync,
    job_should_run,
    mirror_job_state,
)
from apps.event.tests.helpers import make_member, make_registration, make_ticket
from apps.event.tests.services.registration_sheet.scheduler.test_registration_sheet_scheduler import (
    _RegistrationSheetSchedulerCase,
)


class RegistrationSheetSchedulerTest(_RegistrationSheetSchedulerCase):
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
