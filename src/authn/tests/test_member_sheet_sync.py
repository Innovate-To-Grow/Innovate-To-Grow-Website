"""Tests for member-to-Google-Sheet sync service."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from authn.models import ContactEmail, ContactPhone, Member, MemberSheetSyncConfig, MemberSheetSyncLog
from authn.services.member_sheet_sync import MemberSyncError, _build_header, _build_row, sync_members_to_sheet


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
                "Date Joined",
                "Last Updated",
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
