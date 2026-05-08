import threading
from unittest.mock import MagicMock, patch

from django.test import TransactionTestCase
from django.utils import timezone

from event.models import Event, RegistrationSheetSyncLog
from event.services.registration_sheet_sync import _flush_pending_sync
from event.tests.helpers import make_event, make_member, make_registration, make_ticket


def _patch_worksheet():
    return patch(
        "event.services.registration_sheet_sync._get_worksheet",
        return_value=MagicMock(append_rows=MagicMock()),
    )


class FlushPendingSyncAtomicIncrementTest(TransactionTestCase):
    def setUp(self):
        self.event = make_event(
            name="Sync Race Event",
            registration_sheet_id="fake-sheet-id",
            registration_sheet_sync_count=5,
        )
        self.ticket = make_ticket(self.event, name="General")
        self.member = make_member(email="sync-race@example.com", first_name="Test", last_name="User")

    @_patch_worksheet()
    @patch("event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_uses_atomic_increment(self, mock_creds, _mock_ws):
        mock_creds.return_value = MagicMock(is_configured=True)
        make_registration(self.member, self.event, self.ticket)

        _flush_pending_sync(str(self.event.pk))

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 6)

    @_patch_worksheet()
    @patch("event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_increments_from_current_db_value(self, mock_creds, _mock_ws):
        mock_creds.return_value = MagicMock(is_configured=True)
        for i in range(3):
            m = make_member(email=f"batch-{i}@example.com", first_name=f"User{i}", last_name="Test")
            make_registration(m, self.event, self.ticket)

        Event.objects.filter(pk=self.event.pk).update(registration_sheet_sync_count=10)

        _flush_pending_sync(str(self.event.pk))

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 13)

    @patch("event.services.registration_sheet_sync.GoogleCredentialConfig.load")
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

    @patch("event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_concurrent_flush_preserves_count(self, mock_creds):
        mock_creds.return_value = MagicMock(is_configured=True)
        self.event.registration_sheet_sync_count = 0
        self.event.save(update_fields=["registration_sheet_sync_count", "updated_at"])

        m1 = make_member(email="concurrent-1@example.com", first_name="One", last_name="User")
        m2 = make_member(email="concurrent-2@example.com", first_name="Two", last_name="User")
        make_registration(m1, self.event, self.ticket)
        make_registration(m2, self.event, self.ticket)

        barrier = threading.Barrier(2, timeout=5)

        original_append = MagicMock()

        def slow_append(*args, **kwargs):
            barrier.wait()
            return original_append(*args, **kwargs)

        mock_worksheet = MagicMock(append_rows=slow_append)

        with patch("event.services.registration_sheet_sync._get_worksheet", return_value=mock_worksheet):
            t1 = threading.Thread(target=_flush_pending_sync, args=[str(self.event.pk)])
            t2 = threading.Thread(target=_flush_pending_sync, args=[str(self.event.pk)])
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        self.event.refresh_from_db()
        self.assertGreaterEqual(self.event.registration_sheet_sync_count, 2)
