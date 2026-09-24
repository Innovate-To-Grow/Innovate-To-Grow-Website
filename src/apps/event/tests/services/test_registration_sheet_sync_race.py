"""Managed reconciliation keeps identity across concurrent and delayed commits."""

import threading
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.event.models import Event, EventRegistration, RegistrationSheetSyncConfig
from apps.event.services.registration_sheet_sync import _flush_pending_sync, sync_registrations_to_sheet
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.event.tests.services.sheet_fakes import FakeWorksheet


class ManagedSyncRaceTests(TransactionTestCase):
    def setUp(self):
        self.event = make_event()
        Event.objects.filter(pk=self.event.pk).update(
            registration_sheet_id="fake-sheet-id", registration_sheet_sync_count=5
        )
        self.event.refresh_from_db()
        RegistrationSheetSyncConfig.objects.update_or_create(event=self.event, defaults={"sync_mode": "manual"})
        self.ticket = make_ticket(self.event)
        self.member = make_member(email="sync-race@example.com")
        self.sheet = FakeWorksheet()
        credentials = SimpleNamespace(
            is_configured=True, get_credentials_info=lambda: {"client_email": "service@example.com"}
        )
        for name, value in (("GoogleCredentialConfig.load", credentials), ("_get_worksheet", self.sheet)):
            mock = patch(f"apps.event.services.registration_sheet_sync.{name}", return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_background_flush_reconciles_count_from_database_truth(self):
        make_registration(self.member, self.event, self.ticket)
        _flush_pending_sync(str(self.event.pk), raise_errors=True)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 1)
        _flush_pending_sync(str(self.event.pk), raise_errors=True)
        self.assertEqual(len(self.sheet.values), 2)

    @skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row-lock semantics")
    def test_concurrent_provider_runs_serialize_and_do_not_duplicate_rows(self):
        make_registration(self.member, self.event, self.ticket)
        first_provider = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        errors = []
        calls = []

        def before_write():
            calls.append(threading.get_ident())
            if len(calls) == 1:
                first_provider.set()
                if not release_first.wait(timeout=10):
                    raise AssertionError("Provider test release timed out")

        def flush(started=None):
            try:
                if started:
                    started.set()
                _flush_pending_sync(str(self.event.pk), raise_errors=True)
            except Exception as exc:
                errors.append(exc)

        self.sheet.spreadsheet.before_write = before_write
        first = threading.Thread(target=flush)
        second = threading.Thread(target=flush, args=(second_started,))
        first.start()
        self.assertTrue(first_provider.wait(timeout=5))
        second.start()
        self.assertTrue(second_started.wait(timeout=5))
        release_first.set()
        first.join(timeout=15)
        second.join(timeout=15)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(self.sheet.values), 2)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 1)
        self.assertEqual(len(calls), 2)

    @skipUnless(connection.vendor == "postgresql", "requires PostgreSQL transaction visibility")
    def test_registration_committed_after_previous_sync_is_reconciled_by_id(self):
        inserted = threading.Event()
        allow_commit = threading.Event()
        errors = []
        identities = []

        def delayed_source_transaction():
            close_old_connections()
            try:
                with transaction.atomic():
                    # Bulk insertion models a delayed external/import transaction without
                    # holding the scheduler configuration lock in this regression.
                    registration = EventRegistration(
                        member=self.member,
                        event=self.event,
                        ticket=self.ticket,
                        attendee_first_name="Late",
                        attendee_last_name="Commit",
                        attendee_email=self.member.email,
                    )
                    EventRegistration.objects.bulk_create([registration])
                    identities.append(str(registration.pk))
                    inserted.set()
                    if not allow_commit.wait(timeout=10):
                        raise AssertionError("Source transaction test release timed out")
            except Exception as exc:
                errors.append(exc)
                inserted.set()
            finally:
                close_old_connections()

        writer = threading.Thread(target=delayed_source_transaction)
        writer.start()
        self.assertTrue(inserted.wait(timeout=5))
        try:
            self.assertEqual(sync_registrations_to_sheet(self.event), 0)
            cutoff = timezone.now()
        finally:
            allow_commit.set()
            writer.join(timeout=15)
        self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        self.assertLessEqual(EventRegistration.objects.get(pk=identities[0]).created_at, cutoff)
        self.assertEqual(sync_registrations_to_sheet(self.event), 1)
        self.assertIn(identities[0], self.sheet.values[1])

    def test_explicit_queued_sync_is_logged_as_manual(self):
        from apps.core.services.background_jobs.worker import claim_jobs
        from apps.event.models import RegistrationSheetSyncLog
        from apps.event.services.registration_sheet_sync import schedule_registration_sync

        make_registration(self.member, self.event, self.ticket)
        job = schedule_registration_sync(self.event, immediate=True)
        job = next(claimed for claimed in claim_jobs(batch_size=100) if claimed.pk == job.pk)
        _flush_pending_sync(str(self.event.pk), raise_errors=True, job=job)
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.sync_type, RegistrationSheetSyncLog.SyncType.FULL)

    @skipUnless(connection.vendor == "postgresql", "requires PostgreSQL advisory locks")
    def test_different_events_cannot_claim_same_initially_empty_worksheet(self):
        from apps.event.services.registration_sheet_sync.provider import lock_destination
        from apps.event.services.registration_sheet_sync.sheets import RegistrationSyncConflict

        first_registration = make_registration(self.member, self.event, self.ticket)
        other_event = make_event(slug="other-sync-event")
        Event.objects.filter(pk=other_event.pk).update(registration_sheet_id="fake-sheet-id")
        other_event.refresh_from_db()
        RegistrationSheetSyncConfig.objects.update_or_create(event=other_event, defaults={"sync_mode": "manual"})
        make_registration(make_member(), other_event, make_ticket(other_event))
        first_provider = threading.Event()
        release_first = threading.Event()
        second_lock_attempted = threading.Event()
        second_done = threading.Event()
        errors = []

        def before_write():
            first_provider.set()
            if not release_first.wait(timeout=10):
                raise AssertionError("Provider test release timed out")

        def tracked_lock(spreadsheet_id, worksheet_id):
            if threading.current_thread().name == "other-event":
                second_lock_attempted.set()
            return lock_destination(spreadsheet_id, worksheet_id)

        def flush(event, done=None):
            close_old_connections()
            try:
                sync_registrations_to_sheet(event)
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()
                if done:
                    done.set()

        self.sheet.spreadsheet.before_write = before_write
        with patch("apps.event.services.registration_sheet_sync.engine.lock_destination", side_effect=tracked_lock):
            first = threading.Thread(target=flush, args=(self.event,))
            second = threading.Thread(target=flush, args=(other_event, second_done), name="other-event")
            first.start()
            self.assertTrue(first_provider.wait(timeout=5))
            second.start()
            self.assertTrue(second_lock_attempted.wait(timeout=5))
            try:
                self.assertFalse(second_done.wait(timeout=0.1))
            finally:
                release_first.set()
                first.join(timeout=15)
                second.join(timeout=15)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RegistrationSyncConflict)
        self.assertIn("different event", str(errors[0]))
        self.assertEqual(len(self.sheet.spreadsheet.batches), 1)
        self.assertIn(str(first_registration.pk), self.sheet.values[1])
