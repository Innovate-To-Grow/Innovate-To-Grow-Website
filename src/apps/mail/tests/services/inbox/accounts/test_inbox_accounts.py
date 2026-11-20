"""``inbox.accounts``: which mailboxes the universal inbox reads, in which order, and which keys it honours."""

from unittest.mock import patch

from django.db.utils import OperationalError, ProgrammingError
from django.test import TestCase

from apps.core.models import MicrosoftGraphMailboxScope
from apps.core.tests.graph_helpers import grant
from apps.mail.services.inbox.reading.accounts import (
    ACCOUNT_UNAVAILABLE_MESSAGE,
    NO_ACCOUNTS_MESSAGE,
    InboxAccount,
    readable_accounts,
    resolve_account,
)
from apps.mail.services.inbox.reading.connection import InboxError
from apps.mail.tests.services.delivery.graph_inbox.helpers import MAILBOX, Permission, graph_config
from apps.mail.tests.services.inbox.accounts.helpers import GRAPH_KEY, UniversalInboxMixin, gmail_account


class ReadableAccountsTests(UniversalInboxMixin, TestCase):
    def test_nothing_configured_reads_nothing(self):
        self.assertEqual(readable_accounts(), [])

    def test_graph_read_scopes_come_first_with_the_sending_mailbox_leading(self):
        config = graph_config()
        grant(config, "alpha@contoso.com", "zeta@contoso.com", permission=Permission.READ)
        grant(config, "send-only@contoso.com", permission=Permission.SEND)
        active = gmail_account("zz@gmail.com")
        opted_in = gmail_account("aa@gmail.com", is_active=False, show_in_inbox=True)

        accounts = readable_accounts()

        self.assertEqual(
            [account.key for account in accounts],
            [
                GRAPH_KEY,
                "graph:alpha@contoso.com",
                "graph:zeta@contoso.com",
                f"imap:{active.pk}",
                f"imap:{opted_in.pk}",
            ],
        )
        self.assertEqual(accounts[0], InboxAccount(GRAPH_KEY, "graph", MAILBOX, "Microsoft Graph"))
        self.assertEqual(
            accounts[3], InboxAccount(f"imap:{active.pk}", "imap", "zz@gmail.com", "imap.gmail.com", active.pk)
        )

    def test_send_only_scopes_are_not_read(self):
        graph_config(permission=Permission.SEND)

        self.assertEqual(readable_accounts(), [])

    def test_an_inactive_graph_config_is_not_read(self):
        graph_config(is_active=False)

        self.assertEqual(readable_accounts(), [])

    def test_the_active_gmail_account_leads_the_imap_accounts(self):
        opted_in = gmail_account("aa@gmail.com", is_active=False, show_in_inbox=True)
        active = gmail_account("zz@gmail.com")

        self.assertEqual([account.key for account in readable_accounts()], [f"imap:{active.pk}", f"imap:{opted_in.pk}"])

    def test_inactive_gmail_accounts_without_show_in_inbox_are_left_out(self):
        gmail_account("hidden@gmail.com", is_active=False, show_in_inbox=False)

        self.assertEqual(readable_accounts(), [])

    def test_unconfigured_gmail_accounts_are_left_out(self):
        gmail_account("nopass@gmail.com", gmail_password="")
        gmail_account("nohost@gmail.com", is_active=False, show_in_inbox=True, imap_host="")

        self.assertEqual(readable_accounts(), [])

    def test_one_login_is_read_once(self):
        active = gmail_account("i2g@gmail.com")
        gmail_account(" I2G@Gmail.com ", is_active=False, show_in_inbox=True, imap_host="IMAP.gmail.com ")
        other_host = gmail_account("i2g@gmail.com", is_active=False, show_in_inbox=True, imap_host="imap.other.com")

        self.assertEqual(
            [account.key for account in readable_accounts()], [f"imap:{active.pk}", f"imap:{other_host.pk}"]
        )

    def test_missing_tables_are_an_inbox_error(self):
        for error in (OperationalError("no such table"), ProgrammingError("relation does not exist")):
            with (
                self.subTest(type(error).__name__),
                patch("apps.mail.services.inbox.reading.accounts.MicrosoftGraphProviderConfig.load", side_effect=error),
                self.assertRaisesMessage(InboxError, "Run the latest migrations first."),
            ):
                readable_accounts()


class InboxAccountLabelTests(TestCase):
    def test_graph_account(self):
        account = InboxAccount(GRAPH_KEY, "graph", MAILBOX, "Microsoft Graph")

        self.assertTrue(account.is_graph)
        self.assertEqual((account.source_label, account.label), ("Source", f"{MAILBOX} (Microsoft Graph)"))

    def test_imap_account(self):
        account = InboxAccount("imap:1", "imap", "i2g@gmail.com", "imap.gmail.com", 1)

        self.assertFalse(account.is_graph)
        self.assertEqual((account.source_label, account.label), ("IMAP host", "i2g@gmail.com (Gmail IMAP)"))


class ResolveAccountTests(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()

    def test_no_key_is_the_default_account(self):
        for key in (None, ""):
            with self.subTest(key=key):
                self.assertEqual(resolve_account(key).key, GRAPH_KEY)

    def test_a_listed_key_names_its_account(self):
        account = resolve_account(f"imap:{self.gmail.pk}")

        self.assertEqual(
            (account.kind, account.address, account.gmail_account_id), ("imap", "i2g@gmail.com", self.gmail.pk)
        )

    def test_any_other_key_is_refused(self):
        hidden = gmail_account("hidden@gmail.com", is_active=False)
        for key in ("bogus", "imap:999999", f"imap:{hidden.pk}", "graph:other@contoso.com", "all"):
            with self.subTest(key=key), self.assertRaisesMessage(InboxError, ACCOUNT_UNAVAILABLE_MESSAGE):
                resolve_account(key)

    def test_without_any_account_nothing_resolves(self):
        self.gmail.delete()
        # The Graph config stays, but may no longer read.
        MicrosoftGraphMailboxScope.objects.update(permission=Permission.SEND)

        for key in (None, GRAPH_KEY):
            with self.subTest(key=key), self.assertRaisesMessage(InboxError, NO_ACCOUNTS_MESSAGE):
                resolve_account(key)
