"""Tests for member-to-Google-Sheet sync service."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, TransactionTestCase

from authn.models import ContactEmail, ContactPhone, Member, MemberSheetSyncConfig, MemberSheetSyncLog
from authn.services.member_sheet_sync import (
    MemberSyncError,
    _build_header,
    _build_row,
    _safe,
    _sync_in_progress,
    _sync_pending,
    sync_members_to_sheet,
)


def _create_member(first="Alice", middle="", last="Smith", org="Acme", title="Dev", active=True):
    member = Member.objects.create_user(
        password="TestPass123!",
        first_name=first,
        middle_name=middle or "",
        last_name=last,
        organization=org,
        title=title,
        is_active=active,
    )
    ContactEmail.objects.create(member=member, email_address=f"{first.lower()}@example.com", email_type="primary")
    return member


def _enable_config(sheet_id="test-sheet-id", auto_sync=True):
    return MemberSheetSyncConfig.objects.create(is_enabled=True, auto_sync_enabled=auto_sync, google_sheet_id=sheet_id)


class BuildHeaderTests(TestCase):
    def test_header_columns(self):
        header = _build_header()
        self.assertEqual(
            header,
            [
                "UUID",
                "First Name",
                "Middle Name",
                "Last Name",
                "Primary Email",
                "Primary Phone",
                "Organization",
                "Title",
                "Date Joined (UTC)",
                "Last Updated (UTC)",
                "Active",
            ],
        )


class BuildRowTests(TestCase):
    def test_basic_row(self):
        member = _create_member()
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[0], str(member.id))
        self.assertEqual(row[1], "Alice")
        self.assertEqual(row[2], "")  # no middle name
        self.assertEqual(row[3], "Smith")
        self.assertEqual(row[4], "alice@example.com")
        self.assertEqual(row[5], "")  # no phone
        self.assertEqual(row[6], "Acme")
        self.assertEqual(row[7], "Dev")
        self.assertEqual(row[10], "Yes")

    def test_middle_name_present(self):
        member = _create_member(first="Bob", middle="James", last="Doe")
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[2], "James")

    def test_inactive_member(self):
        member = _create_member(first="Inactive", active=False)
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[10], "No")

    def test_phone_present(self):
        member = _create_member(first="Phoney")
        ContactPhone.objects.create(member=member, phone_number="2095551234", region="1-US")
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[5], "2095551234")

    def test_missing_email(self):
        member = Member.objects.create_user(
            password="TestPass123!", first_name="NoEmail", last_name="User", is_active=True
        )
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertEqual(row[4], "")


class SyncDisabledTests(TestCase):
    def test_raises_when_not_configured(self):
        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet()

    def test_raises_when_disabled(self):
        MemberSheetSyncConfig.objects.create(is_enabled=False, google_sheet_id="sheet-id")
        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet()

    def test_raises_when_sheet_id_empty(self):
        MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="")
        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet()


@patch("authn.services.member_sheet_sync._get_worksheet")
class FullSyncTests(TestCase):
    def setUp(self):
        _enable_config()

    @patch("authn.services.member_sheet_sync.GoogleCredentialConfig")
    def test_full_replace_calls_clear_and_update(self, mock_cred_cls, mock_get_ws):
        mock_cred = MagicMock()
        mock_cred.is_configured = True
        mock_cred_cls.load.return_value = mock_cred

        mock_ws = MagicMock()
        mock_get_ws.return_value = mock_ws

        m1 = _create_member(first="Alice")
        m2 = _create_member(first="Bob", active=False)

        rows = sync_members_to_sheet(sync_type="full")

        self.assertEqual(rows, 2)
        mock_ws.clear.assert_called_once()
        call_args = mock_ws.update.call_args
        data = call_args[0][0]
        self.assertEqual(data[0], _build_header())
        self.assertEqual(len(data), 3)  # header + 2 rows
        self.assertEqual(data[1][1], "Alice")
        self.assertEqual(data[2][1], "Bob")

        config = MemberSheetSyncConfig.load()
        self.assertEqual(config.sync_count, 2)
        self.assertEqual(config.sync_error, "")
        self.assertIsNotNone(config.synced_at)

        log = MemberSheetSyncLog.objects.first()
        self.assertEqual(log.status, "success")
        self.assertEqual(log.rows_written, 2)

    @patch("authn.services.member_sheet_sync.GoogleCredentialConfig")
    def test_failure_records_error_and_log(self, mock_cred_cls, mock_get_ws):
        mock_cred = MagicMock()
        mock_cred.is_configured = True
        mock_cred_cls.load.return_value = mock_cred

        mock_ws = MagicMock()
        mock_ws.update.side_effect = RuntimeError("API quota exceeded")
        mock_get_ws.return_value = mock_ws

        _create_member()

        with self.assertRaises(MemberSyncError):
            sync_members_to_sheet(sync_type="full")

        config = MemberSheetSyncConfig.load()
        self.assertIn("API quota exceeded", config.sync_error)

        log = MemberSheetSyncLog.objects.first()
        self.assertEqual(log.status, "failed")
        self.assertIn("API quota exceeded", log.error_message)

    @patch("authn.services.member_sheet_sync.GoogleCredentialConfig")
    def test_empty_member_table(self, mock_cred_cls, mock_get_ws):
        mock_cred = MagicMock()
        mock_cred.is_configured = True
        mock_cred_cls.load.return_value = mock_cred

        mock_ws = MagicMock()
        mock_get_ws.return_value = mock_ws

        rows = sync_members_to_sheet(sync_type="full")

        self.assertEqual(rows, 0)
        mock_ws.clear.assert_called_once()
        data = mock_ws.update.call_args[0][0]
        self.assertEqual(len(data), 1)  # header only


class ScheduleMemberSyncTests(TestCase):
    def test_noop_when_not_configured(self):
        from authn.services.member_sheet_sync import schedule_member_sync

        schedule_member_sync()  # should not raise

    @patch("authn.services.member_sheet_sync.threading.Timer")
    def test_noop_when_auto_sync_disabled(self, mock_timer_cls):
        _enable_config(auto_sync=False)

        from authn.services.member_sheet_sync import schedule_member_sync

        schedule_member_sync()
        mock_timer_cls.assert_not_called()

    @patch("authn.services.member_sheet_sync.threading.Timer")
    def test_starts_timer_when_configured(self, mock_timer_cls):
        _enable_config()
        mock_timer = MagicMock()
        mock_timer_cls.return_value = mock_timer

        from authn.services.member_sheet_sync import schedule_member_sync

        schedule_member_sync()

        mock_timer_cls.assert_called_once()
        mock_timer.start.assert_called_once()


class FormulaInjectionTests(TestCase):
    def test_safe_passes_through_plain_text(self):
        self.assertEqual(_safe("Alice"), "Alice")
        self.assertEqual(_safe(""), "")
        self.assertEqual(_safe(None), "")

    def test_safe_escapes_each_trigger(self):
        for trigger in ("=", "+", "-", "@", "\t", "\r"):
            payload = f"{trigger}HACK()"
            self.assertEqual(_safe(payload), f"'{payload}", f"trigger {trigger!r} not escaped")

    def test_build_row_escapes_formula_in_first_name(self):
        member = _create_member(first='=HYPERLINK("https://evil/","x")')
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertTrue(row[1].startswith("'="))

    def test_build_row_escapes_formula_in_organization(self):
        member = _create_member(org="@SUM(A1:A10)")
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertTrue(row[6].startswith("'@"))


class SingletonEnforcementTests(TestCase):
    def test_saving_enabled_config_disables_others(self):
        first = MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="sheet-a")
        second = MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="sheet-b")
        first.refresh_from_db()
        self.assertFalse(first.is_enabled)
        self.assertTrue(second.is_enabled)

    def test_saving_disabled_config_leaves_others_alone(self):
        enabled = MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="sheet-a")
        MemberSheetSyncConfig.objects.create(is_enabled=False, google_sheet_id="sheet-b")
        enabled.refresh_from_db()
        self.assertTrue(enabled.is_enabled)


class InFlightGuardTests(TestCase):
    def setUp(self):
        _enable_config()
        _create_member()

    def tearDown(self):
        _sync_in_progress.clear()
        _sync_pending.clear()

    @patch("authn.services.member_sheet_sync._get_worksheet")
    @patch("authn.services.member_sheet_sync.GoogleCredentialConfig")
    def test_queues_follow_up_when_already_in_flight(self, mock_cred_cls, mock_get_ws):
        mock_cred = MagicMock()
        mock_cred.is_configured = True
        mock_cred_cls.load.return_value = mock_cred

        _sync_in_progress.set()
        try:
            result = sync_members_to_sheet(sync_type="full")
        finally:
            _sync_in_progress.clear()

        self.assertEqual(result, 0)
        self.assertTrue(_sync_pending.is_set())
        mock_get_ws.assert_not_called()

    @patch("authn.services.member_sheet_sync.threading.Timer")
    @patch("authn.services.member_sheet_sync._get_worksheet")
    @patch("authn.services.member_sheet_sync.GoogleCredentialConfig")
    def test_pending_sync_schedules_follow_up_after_active_write_finishes(
        self, mock_cred_cls, mock_get_ws, mock_timer_cls
    ):
        mock_cred = MagicMock()
        mock_cred.is_configured = True
        mock_cred_cls.load.return_value = mock_cred
        mock_ws = MagicMock()
        mock_get_ws.return_value = mock_ws
        mock_timer = MagicMock()
        mock_timer_cls.return_value = mock_timer
        _sync_pending.set()

        result = sync_members_to_sheet(sync_type="full")

        self.assertEqual(result, 1)
        self.assertFalse(_sync_pending.is_set())
        self.assertFalse(_sync_in_progress.is_set())
        mock_timer_cls.assert_called_once()
        self.assertEqual(mock_timer_cls.call_args.args[0], 0)
        mock_timer.start.assert_called_once()


class SignalSchedulingTests(TransactionTestCase):
    """post_save / post_delete on Member, ContactEmail, ContactPhone fire schedule_member_sync."""

    @patch("authn.services.member_sheet_sync.schedule_member_sync")
    def test_member_save_triggers_schedule(self, mock_schedule):
        Member.objects.create_user(password="TestPass123!", first_name="Sig", last_name="Nal")
        self.assertTrue(mock_schedule.called)

    @patch("authn.services.member_sheet_sync.schedule_member_sync")
    def test_member_delete_triggers_schedule(self, mock_schedule):
        member = Member.objects.create_user(password="TestPass123!", first_name="Del", last_name="Me")
        mock_schedule.reset_mock()
        member.delete()
        self.assertTrue(mock_schedule.called)

    @patch("authn.services.member_sheet_sync.schedule_member_sync")
    def test_contact_email_save_triggers_schedule(self, mock_schedule):
        member = Member.objects.create_user(password="TestPass123!", first_name="Ce", last_name="Mail")
        mock_schedule.reset_mock()
        ContactEmail.objects.create(member=member, email_address="ce@example.com", email_type="primary")
        self.assertTrue(mock_schedule.called)

    @patch("authn.services.member_sheet_sync.schedule_member_sync")
    def test_contact_phone_save_triggers_schedule(self, mock_schedule):
        member = Member.objects.create_user(password="TestPass123!", first_name="Ph", last_name="One")
        mock_schedule.reset_mock()
        ContactPhone.objects.create(member=member, phone_number="2095551234", region="1-US")
        self.assertTrue(mock_schedule.called)
