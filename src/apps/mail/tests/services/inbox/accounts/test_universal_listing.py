"""``list_all_inbox_messages`` merges every account; ``list_inbox_messages`` / ``fetch_inbox_message`` read one."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.services.email.graph.mailbox import GraphReadBusy, GraphReadError
from apps.mail.services.inbox.accounts import ACCOUNT_UNAVAILABLE_MESSAGE, NO_ACCOUNTS_MESSAGE
from apps.mail.services.inbox.connection import (
    INBOX_LIST_CACHE_KEY,
    INBOX_MSG_CACHE_PREFIX,
    INBOX_STALE_LIST_CACHE_PREFIX,
    InboxBusy,
    InboxError,
)
from apps.mail.services.inbox.messages import (
    InboxListing,
    fetch_inbox_message,
    list_all_inbox_messages,
    list_inbox_messages,
)
from apps.mail.tests.services.delivery.graph_inbox.test_graph_inbox_backend import (
    MAILBOX,
    MESSAGE_ID,
    RAW_MIME,
    graph_config,
)
from apps.mail.tests.services.inbox.accounts.helpers import (
    FETCH_TARGET,
    GRAPH_KEY,
    LIST_TARGET,
    UniversalInboxMixin,
    gmail_account,
    graph_message,
    imap_message,
)

GRAPH_MESSAGES = [
    graph_message("g-20", "2026-10-20T12:00:00Z"),
    graph_message("g-18", "2026-10-18T12:00:00Z"),
]


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
            self.assertLogs("apps.mail.services.inbox.messages", "WARNING"),
        ):
            listing = list_all_inbox_messages(limit=30)

        self.assertEqual(listing.unavailable, [MAILBOX])
        self.assertEqual([message["uid"] for message in listing.messages], ["i-21", "i-19"])
        self.assertIsNone(cache.get(f"{INBOX_LIST_CACHE_KEY}:{GRAPH_KEY}:INBOX:30"))

    def test_an_unexpected_failure_is_logged_and_named(self):
        with (
            patch(LIST_TARGET, autospec=True, side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.services.inbox.messages", "ERROR"),
        ):
            listing = list_all_inbox_messages(limit=30)

        self.assertEqual(listing.unavailable, [MAILBOX])
        self.assertEqual(len(listing.messages), 2)

    def test_every_account_failing_is_an_inbox_error(self):
        self.imap.answer(self.imap_key, error=InboxError("IMAP login failed."))

        with (
            patch(LIST_TARGET, autospec=True, side_effect=GraphReadError("Graph refused the read.")),
            self.assertLogs("apps.mail.services.inbox.messages", "WARNING"),
            self.assertRaisesMessage(InboxError, "No inbox account could be read."),
        ):
            list_all_inbox_messages(limit=30)

    def test_no_account_is_an_inbox_error(self):
        self.gmail.delete()
        MicrosoftGraphProviderConfig.objects.all().delete()

        with self.assertRaisesMessage(InboxError, NO_ACCOUNTS_MESSAGE):
            list_all_inbox_messages()
        self.open_inbox.assert_not_called()


class OneAccountRoutingTests(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"

    def test_list_with_an_imap_key_reads_that_account_only(self):
        self.imap.answer(self.imap_key, [imap_message("i-21", 21)])

        with patch(LIST_TARGET) as graph_list:
            results = list_inbox_messages(limit=30, account=self.imap_key)

        graph_list.assert_not_called()
        self.assertEqual(self.open_inbox.call_args.kwargs["account"].key, self.imap_key)
        self.assertEqual([(item["uid"], item["account"]) for item in results], [("i-21", self.imap_key)])

    def test_list_without_a_key_reads_the_default_account(self):
        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES):
            results = list_inbox_messages(limit=30)

        self.open_inbox.assert_not_called()
        self.assertEqual({item["account"] for item in results}, {GRAPH_KEY})

    def test_fetch_with_an_imap_key_opens_that_account(self):
        self.imap.answer(self.imap_key, [imap_message("42", 21)])

        with patch(FETCH_TARGET) as graph_fetch:
            detail = fetch_inbox_message("42", account=self.imap_key)

        graph_fetch.assert_not_called()
        self.assertEqual((detail["uid"], detail["account"]), ("42", self.imap_key))
        self.assertEqual(cache.get(f"{INBOX_MSG_CACHE_PREFIX}{self.imap_key}:INBOX:42"), detail)

    def test_fetch_with_a_graph_key_reads_that_mailbox(self):
        with patch(FETCH_TARGET, autospec=True, return_value=RAW_MIME) as graph_fetch:
            detail = fetch_inbox_message(MESSAGE_ID, account=GRAPH_KEY)

        self.open_inbox.assert_not_called()
        self.assertEqual(graph_fetch.call_args.args[0].mailbox, MAILBOX)
        self.assertEqual((detail["account"], detail["account_address"]), (GRAPH_KEY, MAILBOX))

    def test_the_same_uid_is_cached_per_account(self):
        cache.set(f"{INBOX_MSG_CACHE_PREFIX}{GRAPH_KEY}:INBOX:42", {"uid": "42", "subject": "graph"})
        cache.set(f"{INBOX_MSG_CACHE_PREFIX}{self.imap_key}:INBOX:42", {"uid": "42", "subject": "imap"})

        self.assertEqual(fetch_inbox_message("42", account=GRAPH_KEY)["subject"], "graph")
        self.assertEqual(fetch_inbox_message("42", account=self.imap_key)["subject"], "imap")

    def test_an_unknown_key_reads_nothing(self):
        with patch(LIST_TARGET) as graph_list, patch(FETCH_TARGET) as graph_fetch:
            for key in ("bogus", "imap:999999", "graph:other@contoso.com"):
                with self.subTest(key=key):
                    with self.assertRaisesMessage(InboxError, ACCOUNT_UNAVAILABLE_MESSAGE):
                        list_inbox_messages(account=key)
                    with self.assertRaisesMessage(InboxError, ACCOUNT_UNAVAILABLE_MESSAGE):
                        fetch_inbox_message("42", account=key)

        graph_list.assert_not_called()
        graph_fetch.assert_not_called()
        self.open_inbox.assert_not_called()
