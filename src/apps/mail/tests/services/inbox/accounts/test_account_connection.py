"""``connection.get_account_config`` / ``_open_inbox(account=...)``: an IMAP account logs in with its own row."""

from unittest.mock import Mock, patch

from django.db.utils import OperationalError
from django.test import TestCase

from apps.core.models import GmailAccessAccount
from apps.mail.services.inbox.reading.accounts import InboxAccount
from apps.mail.services.inbox.reading.connection import InboxError, _open_inbox, get_account_config
from apps.mail.tests.services.inbox.accounts.helpers import gmail_account


def account_for(row):
    return InboxAccount(f"imap:{row.pk}", "imap", row.gmail_username, row.imap_host, row.pk)


class GetAccountConfigTests(TestCase):
    def setUp(self):
        GmailAccessAccount.objects.all().delete()
        self.active = gmail_account("active@gmail.com")

    def test_no_account_is_the_active_gmail_account(self):
        self.assertEqual(get_account_config(None), self.active)

    def test_an_opted_in_account_is_its_own_row(self):
        opted_in = gmail_account("other@gmail.com", is_active=False, show_in_inbox=True)

        self.assertEqual(get_account_config(account_for(opted_in)), opted_in)

    def test_a_row_no_longer_readable_is_refused(self):
        hidden = gmail_account("hidden@gmail.com", is_active=False)
        unconfigured = gmail_account("nopass@gmail.com", is_active=False, show_in_inbox=True, gmail_password="")
        deleted = account_for(gmail_account("gone@gmail.com", is_active=False, show_in_inbox=True))
        GmailAccessAccount.objects.filter(pk=deleted.gmail_account_id).delete()

        for account in (account_for(hidden), account_for(unconfigured), deleted):
            with self.subTest(account.address), self.assertRaisesMessage(InboxError, "not available in the Inbox"):
                get_account_config(account)

    def test_missing_tables_are_an_inbox_error(self):
        with (
            patch(
                "apps.mail.services.inbox.reading.connection.GmailAccessAccount.objects.filter",
                side_effect=OperationalError,
            ),
            self.assertRaisesMessage(InboxError, "Run the latest migrations first."),
        ):
            get_account_config(account_for(self.active))

    def test_open_inbox_logs_in_as_the_named_account(self):
        opted_in = gmail_account(
            "other@gmail.com", is_active=False, show_in_inbox=True, imap_host="imap.other.com", gmail_password="pw-2"
        )
        login_context = Mock()
        login_context.__enter__ = Mock(return_value=Mock())
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with patch("apps.mail.services.inbox.reading.connection.MailBox", return_value=mailbox_client) as mailbox_class:
            with _open_inbox(account=account_for(opted_in)):
                pass

        self.assertEqual(mailbox_class.call_args.args, ("imap.other.com",))
        mailbox_client.login.assert_called_once_with("other@gmail.com", "pw-2", initial_folder="INBOX")
