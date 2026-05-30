"""Coverage for member_sheet_sync internals: sheets, scheduler, rows."""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, MemberSheetSyncConfig
from apps.authn.services.member_sheet_sync.rows import build_row
from apps.authn.services.member_sheet_sync.scheduler import (
    _flush_pending_sync,
    schedule_immediate_sync,
    schedule_member_sync,
)
from apps.authn.services.member_sheet_sync.sheets import MemberSyncError, _get_worksheet

Member = get_user_model()


def _member(**kw):
    member = Member.objects.create_user(
        password="StrongPass123!",
        first_name=kw.pop("first_name", "Alice"),
        last_name=kw.pop("last_name", "Smith"),
        **kw,
    )
    ContactEmail.objects.create(member=member, email_address="alice@example.com", email_type="primary")
    return member


class GetWorksheetTests(TestCase):
    def _config(self, **kw):
        return MemberSheetSyncConfig.objects.create(
            is_enabled=True, google_sheet_id=kw.pop("google_sheet_id", "sheet-id"), **kw
        )

    @patch("apps.authn.services.member_sheet_sync.GoogleCredentialConfig.load")
    def test_raises_when_credentials_not_configured(self, mock_load):
        cred = MagicMock()
        cred.is_configured = False
        mock_load.return_value = cred
        with self.assertRaises(MemberSyncError):
            _get_worksheet(self._config())

    @patch("gspread.service_account_from_dict")
    @patch("apps.authn.services.member_sheet_sync.GoogleCredentialConfig.load")
    def test_returns_sheet1_when_no_gid(self, mock_load, mock_gspread):
        cred = MagicMock()
        cred.is_configured = True
        cred.get_credentials_info.return_value = {"type": "service_account"}
        mock_load.return_value = cred

        sheet1 = MagicMock()
        spreadsheet = MagicMock()
        spreadsheet.sheet1 = sheet1
        mock_gspread.return_value.open_by_key.return_value = spreadsheet

        result = _get_worksheet(self._config())
        self.assertEqual(result, sheet1)

    @patch("gspread.service_account_from_dict")
    @patch("apps.authn.services.member_sheet_sync.GoogleCredentialConfig.load")
    def test_finds_worksheet_by_gid(self, mock_load, mock_gspread):
        cred = MagicMock()
        cred.is_configured = True
        cred.get_credentials_info.return_value = {"type": "service_account"}
        mock_load.return_value = cred

        ws = MagicMock()
        ws.id = 42
        spreadsheet = MagicMock()
        spreadsheet.worksheets.return_value = [ws]
        mock_gspread.return_value.open_by_key.return_value = spreadsheet

        result = _get_worksheet(self._config(worksheet_gid=42))
        self.assertEqual(result, ws)

    @patch("gspread.service_account_from_dict")
    @patch("apps.authn.services.member_sheet_sync.GoogleCredentialConfig.load")
    def test_raises_when_gid_not_found(self, mock_load, mock_gspread):
        cred = MagicMock()
        cred.is_configured = True
        cred.get_credentials_info.return_value = {"type": "service_account"}
        mock_load.return_value = cred

        spreadsheet = MagicMock()
        spreadsheet.worksheets.return_value = []
        mock_gspread.return_value.open_by_key.return_value = spreadsheet

        with self.assertRaises(MemberSyncError):
            _get_worksheet(self._config(worksheet_gid=99))


class SyncMembersErrorTests(TestCase):
    def setUp(self):
        MemberSheetSyncConfig.objects.create(is_enabled=True, auto_sync_enabled=True, google_sheet_id="sheet-id")
        from apps.authn.services.member_sheet_sync import _sync_in_progress, _sync_pending

        _sync_in_progress.clear()
        _sync_pending.clear()

    @patch("apps.authn.services.member_sheet_sync._get_worksheet")
    def test_member_sync_error_is_reraised_and_logged(self, mock_get_ws):
        from apps.authn.models import MemberSheetSyncLog
        from apps.authn.services.member_sheet_sync import sync_members_to_sheet

        mock_get_ws.side_effect = MemberSyncError("worksheet missing")
        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet(sync_type="full")

        # A failure log row is recorded (record_sync_failure ran before re-raise).
        self.assertTrue(MemberSheetSyncLog.objects.filter(status=MemberSheetSyncLog.Status.FAILED).exists())


class BuildRowPhoneTests(TestCase):
    def test_build_row_unprefetched_phone_lookup(self):
        # member fetched without prefetch -> build_row queries contact_phones.first() (lines 30-31).
        member = _member()
        ContactPhone.objects.create(member=member, phone_number="2095551234", region="1-US")
        fresh = Member.objects.get(pk=member.pk)
        row = build_row(fresh)
        self.assertIn("2095551234", row)


class SchedulerTests(TestCase):
    def setUp(self):
        # _flush_pending_sync runs in a background Timer thread in production and
        # calls close_old_connections() to refresh that thread's DB handle. The
        # direct synchronous calls below would otherwise close the test's own
        # connection — harmless on SQLite but raises InterfaceError on
        # PostgreSQL (and corrupts later tests in this class via ordering).
        patcher = patch("apps.authn.services.member_sheet_sync.scheduler.close_old_connections")
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("apps.authn.services.member_sheet_sync.threading.Timer")
    def test_schedule_immediate_sync_starts_timer(self, mock_timer_cls):
        mock_timer = MagicMock()
        mock_timer_cls.return_value = mock_timer
        schedule_immediate_sync()
        mock_timer.start.assert_called_once()
        self.assertTrue(mock_timer.daemon)

    @patch("apps.authn.services.member_sheet_sync.threading.Timer")
    def test_schedule_member_sync_cancels_existing_timer(self, mock_timer_cls):
        MemberSheetSyncConfig.objects.create(is_enabled=True, auto_sync_enabled=True, google_sheet_id="sheet-id")
        first = MagicMock()
        second = MagicMock()
        mock_timer_cls.side_effect = [first, second]
        schedule_member_sync()
        schedule_member_sync()
        first.cancel.assert_called_once()
        second.start.assert_called_once()

    @patch("apps.authn.services.member_sheet_sync.sync_members_to_sheet")
    def test_flush_pending_sync_runs_sync(self, mock_sync):
        _flush_pending_sync()
        mock_sync.assert_called_once()

    @patch(
        "apps.authn.services.member_sheet_sync.sync_members_to_sheet",
        side_effect=RuntimeError("sheets down"),
    )
    def test_flush_pending_sync_swallows_errors(self, mock_sync):
        # Should not raise — the except branch logs and the finally still runs.
        _flush_pending_sync()
        mock_sync.assert_called_once()
