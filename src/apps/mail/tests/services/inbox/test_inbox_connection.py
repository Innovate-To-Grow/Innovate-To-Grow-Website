from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db.utils import OperationalError
from django.test import TestCase

from apps.core.models import GmailAccessAccount
from apps.mail.services.inbox.connection import (
    InboxError,
    _open_inbox,
    get_gmail_config,
    resolve_mailbox,
)


class InboxConnectionTests(TestCase):
    def setUp(self):
        self.config = GmailAccessAccount.objects.create(
            name="Gmail",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )

    def test_get_gmail_config_returns_configured_account(self):
        self.assertEqual(get_gmail_config().gmail_username, "campaigns@ucmerced.edu")

    def test_get_gmail_config_raises_on_db_error(self):
        with patch(
            "apps.mail.services.inbox.connection.GmailAccessAccount.load",
            side_effect=OperationalError("no such table"),
        ):
            with self.assertRaisesMessage(InboxError, "Gmail configuration is unavailable"):
                get_gmail_config()

    def test_get_gmail_config_raises_when_not_configured(self):
        with patch(
            "apps.mail.services.inbox.connection.GmailAccessAccount.load",
            return_value=SimpleNamespace(is_configured=False),
        ):
            with self.assertRaisesMessage(InboxError, "No active Gmail import account is configured."):
                get_gmail_config()

    def test_resolve_mailbox_delegates_to_gmail_resolver(self):
        with patch(
            "apps.mail.services.gmail_import.resolve_gmail_mailbox", return_value="resolved@example.com"
        ) as mock_resolve:
            self.assertEqual(resolve_mailbox("requested@example.com"), "resolved@example.com")
        mock_resolve.assert_called_once_with("requested@example.com")

    def test_open_inbox_yields_logged_in_client(self):
        login_context = Mock()
        login_client = Mock()
        login_context.__enter__ = Mock(return_value=login_client)
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", return_value=mailbox_client) as mock_mailbox,
        ):
            with _open_inbox() as client:
                self.assertIs(client, login_client)

        # Each session connects with the gmail_imap channel's timeout (DELIVERY_RATES).
        mock_mailbox.assert_called_once_with("imap.gmail.com", timeout=30)
        mailbox_client.login.assert_called_once_with("campaigns@ucmerced.edu", "app-password", initial_folder="INBOX")

    def test_open_inbox_sent_selects_sent_folder(self):
        login_context = Mock()
        login_client = Mock()
        login_context.__enter__ = Mock(return_value=login_client)
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", return_value=mailbox_client),
            patch("apps.mail.services.gmail_import.connection.select_sent_folder") as mock_select,
        ):
            with _open_inbox(folder="SENT") as client:
                self.assertIs(client, login_client)

        # Sent mailbox name is provider-specific, so login starts folderless then selects it.
        mailbox_client.login.assert_called_once_with("campaigns@ucmerced.edu", "app-password", initial_folder=None)
        mock_select.assert_called_once_with(login_client)

    def test_open_inbox_sent_missing_folder_raises_inbox_error(self):
        from apps.mail.services.gmail_import.connection import GmailImportError

        login_context = Mock()
        login_client = Mock()
        login_context.__enter__ = Mock(return_value=login_client)
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", return_value=mailbox_client),
            patch(
                "apps.mail.services.gmail_import.connection.select_sent_folder",
                side_effect=GmailImportError("no sent folder"),
            ),
        ):
            with self.assertRaisesMessage(InboxError, "no sent folder"):
                with _open_inbox(folder="SENT"):
                    pass

    def test_open_inbox_wraps_connection_failure(self):
        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", side_effect=RuntimeError("no connection")),
        ):
            with self.assertRaisesMessage(InboxError, "Unable to connect to inbox for campaigns@ucmerced.edu."):
                with _open_inbox():
                    pass

    def test_open_inbox_reraises_inbox_error_from_body(self):
        login_context = Mock()
        login_client = Mock()
        login_context.__enter__ = Mock(return_value=login_client)
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", return_value=mailbox_client),
        ):
            # An InboxError raised inside the with-body must propagate unchanged,
            # not be re-wrapped as a connection failure.
            with self.assertRaisesMessage(InboxError, "downstream failure"):
                with _open_inbox():
                    raise InboxError("downstream failure")
