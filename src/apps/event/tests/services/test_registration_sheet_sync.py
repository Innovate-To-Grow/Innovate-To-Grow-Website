from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.event.models import Event, RegistrationSheetSyncLog
from apps.event.services.registration_sheet_sync import (
    RegistrationSyncError,
    sync_registrations_to_sheet,
)
from apps.event.services.registration_sheet_sync.append import (
    _flush_pending_sync,
    _record_append_exception,
    _record_empty_append,
)
from apps.event.services.registration_sheet_sync.logs import record_sync_failure
from apps.event.services.registration_sheet_sync.rows import build_header, build_row
from apps.event.services.registration_sheet_sync.sheets import (
    _get_worksheet,
    _get_worksheet_by_gid,
)
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket


class FullSyncTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Full Sync Event")
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="full-sync@example.com", first_name="Ada", last_name="Lovelace")

    def test_missing_sheet_id_raises_and_logs_failure(self):
        with self.assertRaises(RegistrationSyncError):
            sync_registrations_to_sheet(self.event)

        self.event.refresh_from_db()
        self.assertIn("not configured", self.event.registration_sheet_sync_error)
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.FAILED)
        self.assertEqual(log.sync_type, RegistrationSheetSyncLog.SyncType.FULL)

    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_unconfigured_credentials_raises_and_logs(self, mock_load):
        mock_load.return_value = MagicMock(is_configured=False)
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])

        with self.assertRaises(RegistrationSyncError):
            sync_registrations_to_sheet(self.event)

        self.event.refresh_from_db()
        self.assertIn("No active Google service account", self.event.registration_sheet_sync_error)
        self.assertEqual(RegistrationSheetSyncLog.objects.filter(event=self.event).count(), 1)

    @patch("apps.event.services.registration_sheet_sync._get_worksheet")
    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_successful_full_sync_writes_rows_and_updates_event(self, mock_load, mock_worksheet):
        mock_load.return_value = MagicMock(is_configured=True)
        worksheet = MagicMock()
        mock_worksheet.return_value = worksheet
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])
        make_registration(
            self.member,
            self.event,
            self.ticket,
            attendee_first_name="Ada",
            attendee_last_name="Lovelace",
            attendee_email="full-sync@example.com",
        )

        count = sync_registrations_to_sheet(self.event)

        self.assertEqual(count, 1)
        worksheet.clear.assert_called_once()
        worksheet.update.assert_called_once()
        rows_arg = worksheet.update.call_args.args[0]
        self.assertEqual(rows_arg[0][0], "Order")
        self.assertEqual(len(rows_arg), 2)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 1)
        self.assertEqual(self.event.registration_sheet_sync_error, "")
        self.assertIsNotNone(self.event.registration_sheet_synced_at)
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.SUCCESS)
        self.assertEqual(log.rows_written, 1)

    @patch("apps.event.services.registration_sheet_sync._get_worksheet", side_effect=RegistrationSyncError("gid gone"))
    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_registration_sync_error_reraised_and_logged(self, mock_load, _mock_ws):
        mock_load.return_value = MagicMock(is_configured=True)
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])

        with self.assertRaises(RegistrationSyncError) as ctx:
            sync_registrations_to_sheet(self.event)

        self.assertIn("gid gone", str(ctx.exception))
        self.event.refresh_from_db()
        self.assertIn("gid gone", self.event.registration_sheet_sync_error)

    @patch("apps.event.services.registration_sheet_sync._get_worksheet")
    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_unexpected_error_wrapped_in_registration_sync_error(self, mock_load, mock_worksheet):
        mock_load.return_value = MagicMock(is_configured=True)
        worksheet = MagicMock()
        worksheet.clear.side_effect = RuntimeError("network down")
        mock_worksheet.return_value = worksheet
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])

        with self.assertRaises(RegistrationSyncError) as ctx:
            sync_registrations_to_sheet(self.event)

        self.assertIn("Failed to write to Google Sheet", str(ctx.exception))
        self.event.refresh_from_db()
        self.assertIn("network down", self.event.registration_sheet_sync_error)


class SheetsHelperTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Sheets Event", registration_sheet_id="sheet-id")

    def test_get_worksheet_by_gid_returns_match(self):
        ws_a = MagicMock(id=10)
        ws_b = MagicMock(id=20)
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[ws_a, ws_b]))
        self.assertIs(_get_worksheet_by_gid(spreadsheet, 20), ws_b)

    def test_get_worksheet_by_gid_returns_none_when_missing(self):
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1)]))
        self.assertIsNone(_get_worksheet_by_gid(spreadsheet, 999))

    @patch("apps.event.services.registration_sheet_sync.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_unconfigured_raises(self, mock_load):
        mock_load.return_value = MagicMock(is_configured=False)
        with self.assertRaises(RegistrationSyncError):
            _get_worksheet(self.event)

    @patch("apps.event.services.registration_sheet_sync.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_uses_sheet1_when_no_gid(self, mock_load):
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        sheet1 = MagicMock()
        client = MagicMock()
        client.open_by_key.return_value = MagicMock(sheet1=sheet1)
        with patch("gspread.service_account_from_dict", return_value=client):
            result = _get_worksheet(self.event)
        self.assertIs(result, sheet1)

    @patch("apps.event.services.registration_sheet_sync.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_resolves_by_gid(self, mock_load):
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        self.event.registration_sheet_gid = 42
        self.event.save(update_fields=["registration_sheet_gid", "updated_at"])
        target = MagicMock(id=42)
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[target]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            result = _get_worksheet(self.event)
        self.assertIs(result, target)

    @patch("apps.event.services.registration_sheet_sync.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_missing_gid_raises(self, mock_load):
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        self.event.registration_sheet_gid = 7
        self.event.save(update_fields=["registration_sheet_gid", "updated_at"])
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1)]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(RegistrationSyncError) as ctx:
                _get_worksheet(self.event)
        self.assertIn("GID not found", str(ctx.exception))


class RowsHelperTest(TestCase):
    def test_build_header_includes_optional_columns(self):
        event = make_event(collect_phone=True, allow_secondary_email=True)
        header = build_header(event, ["Q1"])
        self.assertIn("Phone", header)
        self.assertIn("Membership Secondary", header)
        self.assertEqual(header[-1], "Q1")

    def test_build_header_omits_optional_columns(self):
        event = make_event(collect_phone=False, allow_secondary_email=False)
        header = build_header(event, [])
        self.assertNotIn("Phone", header)
        self.assertNotIn("Membership Secondary", header)

    def test_build_row_includes_phone_and_secondary_and_answers(self):
        event = make_event(collect_phone=True, allow_secondary_email=True)
        ticket = make_ticket(event, name="GA")
        member = make_member(email="row@example.com")
        registration = make_registration(
            member,
            event,
            ticket,
            attendee_first_name="Ada",
            attendee_last_name="Lovelace",
            attendee_phone="+15551234567",
            attendee_email="row@example.com",
            attendee_secondary_email="row2@example.com",
            question_answers=[{"question_text": "Q1", "answer": "Yes"}],
        )

        row = build_row(registration, event, ["Q1"], 5)

        self.assertEqual(row[0], "5")
        self.assertIn("+15551234567", row)
        self.assertIn("row2@example.com", row)
        self.assertEqual(row[-1], "Yes")

    def test_build_row_omits_optional_fields_and_blank_answer(self):
        event = make_event(collect_phone=False, allow_secondary_email=False)
        ticket = make_ticket(event, name="GA")
        member = make_member(email="row-min@example.com")
        registration = make_registration(member, event, ticket)

        row = build_row(registration, event, ["Missing"], 1)

        self.assertEqual(row[-1], "")
        self.assertNotIn("+15551234567", row)


class LogsHelperTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Logs Event")

    def test_record_sync_failure_without_sync_type_skips_log(self):
        record_sync_failure(self.event, "oops")

        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_error, "oops")
        self.assertFalse(RegistrationSheetSyncLog.objects.filter(event=self.event).exists())

    def test_record_sync_failure_updates_synced_at_and_rows(self):
        record_sync_failure(
            self.event,
            "broke",
            sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
            update_synced_at=True,
            rows_written=0,
        )

        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.registration_sheet_synced_at)
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.FAILED)
        self.assertEqual(log.error_message, "broke")
        self.assertEqual(log.rows_written, 0)


class AppendBranchTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Append Event")

    def test_schedule_sync_noop_without_sheet_id(self):
        from apps.event.services.registration_sheet_sync.append import schedule_registration_sync

        with patch("apps.event.services.registration_sheet_sync.append.threading.Timer") as timer:
            schedule_registration_sync(self.event)
        timer.assert_not_called()

    def test_schedule_sync_registers_and_replaces_timer(self):
        from apps.event.services.registration_sheet_sync import append as append_mod
        from apps.event.services.registration_sheet_sync.append import schedule_registration_sync

        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])
        event_id = str(self.event.pk)

        # Patch _flush_pending_sync so a fired timer is a harmless no-op, and keep
        # the debounce long so the timers never actually fire during the test.
        with patch.object(append_mod, "_flush_pending_sync"):
            try:
                schedule_registration_sync(self.event)
                first_timer = append_mod._sync_timers.get(event_id)
                self.assertIsNotNone(first_timer)
                self.assertTrue(first_timer.daemon)
                self.assertTrue(first_timer.is_alive())

                # Calling again cancels the previous timer and registers a new one.
                schedule_registration_sync(self.event)
                second_timer = append_mod._sync_timers.get(event_id)
                self.assertIsNotNone(second_timer)
                self.assertIsNot(second_timer, first_timer)
                # The replaced timer was cancelled (its internal finished flag is set).
                self.assertTrue(first_timer.finished.is_set())
            finally:
                with append_mod._sync_lock:
                    timer = append_mod._sync_timers.pop(event_id, None)
                if timer:
                    timer.cancel()

    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_unconfigured_credentials_records_failure(self, mock_load):
        mock_load.return_value = MagicMock(is_configured=False)
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])

        _flush_pending_sync(str(self.event.pk))

        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.FAILED)
        self.assertEqual(log.sync_type, RegistrationSheetSyncLog.SyncType.APPEND)

    def test_flush_noop_when_event_sheet_id_cleared(self):
        # Event exists but has no sheet id -> early return inside flush body.
        _flush_pending_sync(str(self.event.pk))
        self.assertFalse(RegistrationSheetSyncLog.objects.filter(event=self.event).exists())

    def test_record_empty_append_logs_zero_rows(self):
        _record_empty_append(self.event)
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.rows_written, 0)
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.SUCCESS)

    def test_record_append_exception_logs_failure(self):
        _record_append_exception(str(self.event.pk), RuntimeError("explode"))
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.FAILED)
        self.assertIn("explode", log.error_message)

    def test_record_append_exception_swallows_missing_event(self):
        # event_id that does not exist -> inner Event.DoesNotExist caught and logged.
        missing_id = "00000000-0000-0000-0000-000000000000"
        with patch("apps.event.services.registration_sheet_sync.append.logger.exception") as log_exc:
            _record_append_exception(missing_id, RuntimeError("explode"))
        self.assertTrue(log_exc.called)
        self.assertFalse(RegistrationSheetSyncLog.objects.exists())

    @patch("apps.event.services.registration_sheet_sync._get_worksheet")
    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_first_batch_appends_header(self, mock_load, mock_worksheet):
        mock_load.return_value = MagicMock(is_configured=True)
        worksheet = MagicMock()
        mock_worksheet.return_value = worksheet
        self.event.registration_sheet_id = "sheet-id"
        self.event.registration_sheet_sync_count = 0
        self.event.save(update_fields=["registration_sheet_id", "registration_sheet_sync_count", "updated_at"])
        ticket = make_ticket(self.event, name="GA")
        member = make_member(email="first-batch@example.com", first_name="Ada", last_name="Lovelace")
        make_registration(member, self.event, ticket)

        _flush_pending_sync(str(self.event.pk))

        worksheet.append_rows.assert_called_once()
        rows_arg = worksheet.append_rows.call_args.args[0]
        self.assertEqual(rows_arg[0][0], "Order")
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 1)

    @patch("apps.event.services.registration_sheet_sync._get_worksheet", side_effect=RuntimeError("boom"))
    @patch("apps.event.services.registration_sheet_sync.GoogleCredentialConfig.load")
    def test_flush_worksheet_failure_records_exception(self, mock_load, _mock_ws):
        mock_load.return_value = MagicMock(is_configured=True)
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])
        ticket = make_ticket(self.event, name="GA")
        member = make_member(email="flush-fail@example.com")
        make_registration(member, self.event, ticket)

        _flush_pending_sync(str(self.event.pk))

        log = RegistrationSheetSyncLog.objects.filter(event=self.event).last()
        self.assertEqual(log.status, RegistrationSheetSyncLog.Status.FAILED)
        self.assertIn("boom", log.error_message)

    def test_flush_missing_event_handled(self):
        # event_id that doesn't exist -> Event.DoesNotExist caught by outer except.
        missing_id = "00000000-0000-0000-0000-000000000000"
        with patch("apps.event.services.registration_sheet_sync.append.logger.exception"):
            _flush_pending_sync(missing_id)
        self.assertFalse(Event.objects.filter(pk=missing_id).exists())
