import threading
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection

from apps.event.models import Event, RegistrationSheetSyncConfig
from apps.event.services.registration_sheet_sync import sync_registrations_to_sheet
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.event.tests.services.registration_sheet.managed.test_registration_sheet_sync_race import (
    _ManagedSyncRaceCase,
)


class ManagedSyncRaceTests(_ManagedSyncRaceCase):
    @skipUnless(connection.vendor == "postgresql", "requires PostgreSQL advisory locks")
    def test_different_events_cannot_claim_same_initially_empty_worksheet(self):
        from apps.event.services.registration_sheet_sync.worksheet.sheets import RegistrationSyncConflict
        from apps.event.services.registration_sheet_sync.worksheet.snapshot import lock_destination

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
        with patch(
            "apps.event.services.registration_sheet_sync.sync.prepare.lock_destination", side_effect=tracked_lock
        ):
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
