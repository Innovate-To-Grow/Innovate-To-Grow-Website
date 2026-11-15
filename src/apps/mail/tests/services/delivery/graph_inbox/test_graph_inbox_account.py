from unittest.mock import patch

from django.test import TestCase

from apps.core.models import GmailAccessAccount
from apps.mail.admin.inbox.list_views import _inbox_account
from apps.mail.tests.services.delivery.graph_inbox.test_graph_inbox_backend import MAILBOX, Permission, graph_config
from apps.mail.tests.services.delivery.graph_inbox.test_graph_inbox_messages import GraphInboxFixtureMixin


class InboxAccountTests(GraphInboxFixtureMixin, TestCase):
    def test_graph_account_when_read_is_granted(self):
        graph_config()

        self.assertEqual(
            _inbox_account(),
            {"account": MAILBOX, "source_label": "Source", "source": "Microsoft Graph"},
        )

    def test_gmail_account_otherwise(self):
        graph_config(permission=Permission.SEND)
        GmailAccessAccount.objects.all().delete()
        GmailAccessAccount.objects.create(is_active=True, imap_host="imap.example.com", gmail_username="i2g@gmail.com")

        self.assertEqual(
            _inbox_account(), {"account": "i2g@gmail.com", "source_label": "IMAP host", "source": "imap.example.com"}
        )

    def test_a_reader_failure_falls_back_to_gmail_and_is_logged(self):
        with (
            patch("apps.mail.services.inbox.graph_backend.active_reader", side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.admin.inbox", "ERROR"),
        ):
            account = _inbox_account()

        self.assertEqual(account["source_label"], "IMAP host")
