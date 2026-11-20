"""``list_all_inbox_messages`` merges every account; ``list_inbox_messages`` / ``fetch_inbox_message`` read one."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.services.email.graph.mailbox import GraphReadBusy, GraphReadError
from apps.mail.services.inbox.reading.accounts import NO_ACCOUNTS_MESSAGE
from apps.mail.services.inbox.reading.connection import (
    INBOX_LIST_CACHE_KEY,
    INBOX_STALE_LIST_CACHE_PREFIX,
    InboxBusy,
    InboxError,
)
from apps.mail.services.inbox.reading.listing import InboxListing, list_all_inbox_messages
from apps.mail.tests.services.delivery.graph_inbox.helpers import (
    MAILBOX,
    graph_config,
)
from apps.mail.tests.services.inbox.accounts.helpers import (
    GRAPH_KEY,
    GRAPH_MESSAGES,
    LIST_TARGET,
    UniversalInboxMixin,
    gmail_account,
    imap_message,
)


class ListAllInboxMessagesTests(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"
        self.imap.answer(self.imap_key, [imap_message("i-21", 21), imap_message("i-19", 19)])

    def test_merges_every_account_newest_first_up_to_the_limit(self):
        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES):
            listing = list_all_inbox_messages(limit=3)

        self.assertIsInstance(listing, InboxListing)
        self.assertEqual([message["uid"] for message in listing.messages], ["i-21", "g-20", "i-19"])
        self.assertEqual(
            [(message["account"], message["account_address"]) for message in listing.messages],
            [(self.imap_key, "i2g@gmail.com"), (GRAPH_KEY, MAILBOX), (self.imap_key, "i2g@gmail.com")],
        )
        self.assertEqual((listing.busy, listing.unavailable, listing.showing_stale), ([], [], False))

    def test_each_account_is_read_with_the_limit_and_cached_under_its_own_key(self):
        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES) as graph_list:
            list_all_inbox_messages(limit=15, folder="INBOX")
            again = list_all_inbox_messages(limit=15, folder="INBOX")

        self.assertEqual(graph_list.call_count, 1)
        self.assertEqual(graph_list.call_args.args[1:], ("INBOX", 15))
        self.assertEqual(self.imap.opened, [self.imap_key])
        self.assertEqual(len(again.messages), 4)
        self.assertEqual(len(cache.get(f"{INBOX_LIST_CACHE_KEY}:{GRAPH_KEY}:INBOX:15")), 2)
        self.assertEqual(len(cache.get(f"{INBOX_LIST_CACHE_KEY}:{self.imap_key}:INBOX:15")), 2)

    def test_force_refresh_reads_every_account_again(self):
        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES) as graph_list:
            list_all_inbox_messages(limit=15)
            list_all_inbox_messages(limit=15, force_refresh=True)

        self.assertEqual(graph_list.call_count, 2)
        self.assertEqual(self.imap.opened, [self.imap_key, self.imap_key])

    def test_a_held_back_account_is_named_and_shows_its_last_list(self):
        stale = [{"uid": "old-1", "timestamp": 1.0, "account": self.imap_key}]
        cache.set(f"{INBOX_STALE_LIST_CACHE_PREFIX}{self.imap_key}:INBOX:30", stale)
        self.imap.answer(self.imap_key, error=InboxBusy("Gmail is busy; try again in about 30 seconds.", 30))

        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES):
            listing = list_all_inbox_messages(limit=30)

        self.assertEqual(listing.busy, ["i2g@gmail.com: Gmail is busy; try again in about 30 seconds."])
        self.assertTrue(listing.showing_stale)
        self.assertEqual([message["uid"] for message in listing.messages], ["g-20", "g-18", "old-1"])
        self.assertEqual(listing.unavailable, [])

    def test_a_held_back_account_without_a_last_list_shows_nothing_stale(self):
        with patch(LIST_TARGET, autospec=True, side_effect=GraphReadBusy(30)):
            listing = list_all_inbox_messages(limit=30)

        self.assertEqual(len(listing.busy), 1)
        self.assertTrue(listing.busy[0].startswith(f"{MAILBOX}: "))
        self.assertFalse(listing.showing_stale)
        self.assertEqual([message["uid"] for message in listing.messages], ["i-21", "i-19"])

    def test_a_failing_account_is_named_and_the_others_are_still_listed(self):
        with (
            patch(LIST_TARGET, autospec=True, side_effect=GraphReadError("Graph refused the read.")),
            self.assertLogs("apps.mail.services.inbox.reading.listing", "WARNING"),
        ):
            listing = list_all_inbox_messages(limit=30)

        self.assertEqual(listing.unavailable, [MAILBOX])
        self.assertEqual([message["uid"] for message in listing.messages], ["i-21", "i-19"])
        self.assertIsNone(cache.get(f"{INBOX_LIST_CACHE_KEY}:{GRAPH_KEY}:INBOX:30"))

    def test_an_unexpected_failure_is_logged_and_named(self):
        with (
            patch(LIST_TARGET, autospec=True, side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.services.inbox.reading.listing", "ERROR"),
        ):
            listing = list_all_inbox_messages(limit=30)

        self.assertEqual(listing.unavailable, [MAILBOX])
        self.assertEqual(len(listing.messages), 2)

    def test_every_account_failing_is_an_inbox_error(self):
        self.imap.answer(self.imap_key, error=InboxError("IMAP login failed."))

        with (
            patch(LIST_TARGET, autospec=True, side_effect=GraphReadError("Graph refused the read.")),
            self.assertLogs("apps.mail.services.inbox.reading.listing", "WARNING"),
            self.assertRaisesMessage(InboxError, "No inbox account could be read."),
        ):
            list_all_inbox_messages(limit=30)

    def test_no_account_is_an_inbox_error(self):
        self.gmail.delete()
        MicrosoftGraphProviderConfig.objects.all().delete()

        with self.assertRaisesMessage(InboxError, NO_ACCOUNTS_MESSAGE):
            list_all_inbox_messages()
        self.open_inbox.assert_not_called()
