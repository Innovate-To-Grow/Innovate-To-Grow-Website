from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.authn.models import MemberSheetSyncConfig, MemberSheetSyncLog
from apps.authn.services.members.sheet_sync import (
    MemberSyncError,
    _build_header,
    sync_members_to_sheet,
)
from apps.authn.tests.services.members.sheet_sync.test_member_sheet_sync import _create_member, _enable_config


@patch("apps.authn.services.members.sheet_sync._get_worksheet")
class FullSyncTests(TestCase):
    def setUp(self):
        _enable_config()

    @patch("apps.authn.services.members.sheet_sync.GoogleCredentialConfig")
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

    @patch("apps.authn.services.members.sheet_sync.GoogleCredentialConfig")
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

    @patch("apps.authn.services.members.sheet_sync.GoogleCredentialConfig")
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
