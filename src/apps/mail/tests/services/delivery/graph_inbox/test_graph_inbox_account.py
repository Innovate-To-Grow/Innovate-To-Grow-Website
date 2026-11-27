from unittest.mock import patch

from django.test import TestCase

from apps.core.models import GmailAccessAccount
from apps.mail.admin.inbox.helpers import inbox_account_summary as _inbox_account
from apps.mail.admin.inbox.list_views import _connectable
from apps.mail.services.inbox import ALL_ACCOUNTS, readable_accounts
from apps.mail.tests.services.delivery.graph_inbox.helpers import (
    MAILBOX,
    GraphInboxFixtureMixin,
    Permission,
    graph_config,
)

GRAPH_ACCOUNT = {"account": MAILBOX, "source_label": "Source", "source": "Microsoft Graph"}


class InboxAccountTests(GraphInboxFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        GmailAccessAccount.objects.all().delete()

    def gmail(self, **overrides):
        values = {
            "name": "Gmail",
            "is_active": True,
            "imap_host": "imap.example.com",
            "gmail_username": "i2g@gmail.com",
            "gmail_password": "app-password",
        }
        return GmailAccessAccount.objects.create(**{**values, **overrides})

    def test_graph_account_when_read_is_granted(self):
        graph_config()
        accounts = readable_accounts()

        self.assertEqual(_inbox_account(accounts, ALL_ACCOUNTS), GRAPH_ACCOUNT)
        self.assertEqual(_inbox_account(accounts, f"graph:{MAILBOX}"), GRAPH_ACCOUNT)

    def test_gmail_account_otherwise(self):
        graph_config(permission=Permission.SEND)
        self.gmail()

        self.assertEqual(
            _inbox_account(readable_accounts(), ALL_ACCOUNTS),
            {"account": "i2g@gmail.com", "source_label": "IMAP host", "source": "imap.example.com"},
        )

    def test_every_account_is_summarised_until_one_is_selected(self):
        graph_config()
        row = self.gmail()
        accounts = readable_accounts()

        self.assertEqual(
            _inbox_account(accounts, ALL_ACCOUNTS),
            {"account": "All accounts (2)", "source_label": "Sources", "source": "Microsoft Graph, imap.example.com"},
        )
        self.assertEqual(
            _inbox_account(accounts, f"imap:{row.pk}"),
            {"account": "i2g@gmail.com", "source_label": "IMAP host", "source": "imap.example.com"},
        )

    def test_no_account_is_shown_as_not_configured(self):
        self.assertEqual(
            _inbox_account([], ALL_ACCOUNTS), {"account": "Not configured", "source_label": "Source", "source": "N/A"}
        )

    def test_an_account_listing_failure_is_logged_and_shows_no_account(self):
        with (
            patch("apps.mail.admin.inbox.services.connectable_accounts", side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.admin.inbox", "ERROR"),
        ):
            accounts, hidden = _connectable()

        self.assertEqual((accounts, hidden), ([], []))
        self.assertEqual(_inbox_account(accounts, ALL_ACCOUNTS)["account"], "Not configured")
