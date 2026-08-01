import threading
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.event.models import Event, RegistrationSheetSyncLog
from apps.event.services.registration_sheet_sync import _flush_pending_sync
from apps.event.services.registration_sheet_sync.append import _pending_registrations
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket


def _patch_worksheet():
    return patch(
        "apps.event.services.registration_sheet_sync._get_worksheet",
        return_value=MagicMock(append_rows=MagicMock()),
    )


class FlushPendingSyncCursorTest(TransactionTestCase):
    def setUp(self):
        self.event = make_event(
            name="Sync Race Event",
            registration_sheet_id="fake-sheet-id",
            registration_sheet_sync_count=5,
        )
        self.ticket = make_ticket(self.event, name="General")
        self.member = make_member(email="sync-race@example.com", first_name="Test", last_name="User")

    @_patch_worksheet()
    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_reconciles_count_to_selected_database_rows(self, mock_creds, _mock_ws):
        mock_creds.return_value = MagicMock(is_configured=True)
        make_registration(self.member, self.event, self.ticket)

        _flush_pending_sync(str(self.event.pk))

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 1)

    @_patch_worksheet()
    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_repairs_stale_count_from_database_truth(self, mock_creds, _mock_ws):
        mock_creds.return_value = MagicMock(is_configured=True)
        for i in range(3):
            m = make_member(email=f"batch-{i}@example.com", first_name=f"User{i}", last_name="Test")
            make_registration(m, self.event, self.ticket)

        Event.objects.filter(pk=self.event.pk).update(registration_sheet_sync_count=10)

        _flush_pending_sync(str(self.event.pk))

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 3)

    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_no_new_registrations_updates_timestamp(self, mock_creds):
        mock_creds.return_value = MagicMock(is_configured=True)
        self.event.registration_sheet_synced_at = timezone.now()
        self.event.save(update_fields=["registration_sheet_synced_at", "updated_at"])

        _flush_pending_sync(str(self.event.pk))

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 5)
        self.assertIsNotNone(self.event.registration_sheet_synced_at)
        log = RegistrationSheetSyncLog.objects.filter(event=self.event).last()
        self.assertEqual(log.rows_written, 0)

    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    @skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row-lock semantics")
    def test_concurrent_flush_preserves_count(self, mock_creds):
        mock_creds.return_value = MagicMock(is_configured=True)
        self.event.registration_sheet_sync_count = 0
        self.event.save(update_fields=["registration_sheet_sync_count", "updated_at"])

        m1 = make_member(email="concurrent-1@example.com", first_name="One", last_name="User")
        m2 = make_member(email="concurrent-2@example.com", first_name="Two", last_name="User")
        make_registration(m1, self.event, self.ticket)
        make_registration(m2, self.event, self.ticket)

        first_provider_call = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        sheet_rows = []
        sheet_lock = threading.Lock()

        def read_values():
            with sheet_lock:
                return [list(row) for row in sheet_rows]

        def slow_append(rows, **_kwargs):
            if not first_provider_call.is_set():
                first_provider_call.set()
                release_first.wait(timeout=5)
            with sheet_lock:
                sheet_rows.extend([list(row) for row in rows])

        mock_worksheet = MagicMock()
        mock_worksheet.get_all_values.side_effect = read_values
        mock_worksheet.append_rows.side_effect = slow_append

        with patch("apps.event.services.registration_sheet_sync._get_worksheet", return_value=mock_worksheet):
            t1 = threading.Thread(target=_flush_pending_sync, args=[str(self.event.pk)])
            t2 = threading.Thread(target=lambda: (second_started.set(), _flush_pending_sync(str(self.event.pk))))
            t1.start()
            first_provider_call.wait(timeout=5)
            t2.start()
            second_started.wait(timeout=5)
            release_first.set()
            t1.join(timeout=10)
            t2.join(timeout=10)

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 2)
        self.assertEqual(mock_worksheet.append_rows.call_count, 1)

    @skipUnless(connection.vendor == "postgresql", "requires PostgreSQL transaction visibility")
    def test_registration_committed_after_cutoff_is_reconciled_by_id(self):
        inserted = threading.Event()
        allow_commit = threading.Event()
        errors = []

        def create_before_cutoff_then_commit_late():
            try:
                close_old_connections()
                with transaction.atomic():
                    member = make_member(
                        email="commit-order@example.com",
                        first_name="Commit",
                        last_name="Order",
                    )
                    registration = make_registration(member, self.event, self.ticket)
                    inserted.set()
                    allow_commit.wait(timeout=5)
                    self.assertIsNotNone(registration.created_at)
            except Exception as exc:  # pragma: no cover - surfaced in main thread
                errors.append(exc)
                inserted.set()
            finally:
                close_old_connections()

        writer = threading.Thread(target=create_before_cutoff_then_commit_late)
        writer.start()
        self.assertTrue(inserted.wait(timeout=5))
        cutoff = timezone.now()

        # READ COMMITTED cannot see the row yet, even though its created_at was
        # assigned before this cutoff.
        self.assertEqual(_pending_registrations(self.event, cutoff=cutoff), [])
        Event.objects.filter(pk=self.event.pk).update(registration_sheet_synced_at=cutoff)

        allow_commit.set()
        writer.join(timeout=10)
        self.assertFalse(writer.is_alive())
        if errors:
            raise errors[0]

        self.event.refresh_from_db()
        reconciled = _pending_registrations(self.event, cutoff=cutoff)
        self.assertEqual(len(reconciled), 1)
        self.assertLessEqual(reconciled[0].created_at, cutoff)
