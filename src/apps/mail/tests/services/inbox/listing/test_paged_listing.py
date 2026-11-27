"""The inbox's "Load older" across accounts: every account reads its own page from its own position, the merged
page keeps the newest ``limit`` of them all, and the next page continues each account exactly where it stopped."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.services.email.graph.mailbox import GraphReadError
from apps.mail.services.inbox.reading import paging
from apps.mail.services.inbox.reading.connection import INBOX_LIST_CACHE_KEY, InboxBusy
from apps.mail.services.inbox.reading.listing import list_all_inbox_messages, list_inbox_messages
from apps.mail.tests.services.delivery.graph_inbox.helpers import graph_config
from apps.mail.tests.services.inbox.accounts.helpers import (
    GRAPH_KEY,
    LIST_TARGET,
    UniversalInboxMixin,
    gmail_account,
    graph_message,
    imap_message,
)

# Graph mail on even days of October, Gmail mail (UID = day) on odd days: a merged list alternates.
GRAPH_ALL = [graph_message(f"g-{day}", f"2026-10-{day:02d}T12:00:00Z") for day in (20, 18, 16, 14, 12)]
IMAP_ALL = [imap_message(str(day), day) for day in (11, 13, 15, 17, 19, 21)]


def graph_page(_reader, folder, limit, skip=0):
    return GRAPH_ALL[skip : skip + limit]


class PagedListingTests(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"
        self.imap.answer(self.imap_key, IMAP_ALL)
        patcher = patch(LIST_TARGET, autospec=True, side_effect=graph_page)
        self.graph_list = patcher.start()
        self.addCleanup(patcher.stop)

    def uids(self, listing):
        return [message["uid"] for message in listing.messages]

    def test_pages_continue_every_account_without_gaps_or_repeats(self):
        pages, cursor = [], None
        for _ in range(5):
            listing = list_all_inbox_messages(limit=4, cursor=cursor)
            pages.append(self.uids(listing))
            cursor = listing.cursor
            if not listing.has_older:
                break

        self.assertEqual(
            pages,
            [["21", "g-20", "19", "g-18"], ["17", "g-16", "15", "g-14"], ["13", "g-12", "11"]],
        )
        self.assertEqual(cursor, {GRAPH_KEY: "x", self.imap_key: "x"})
        # Graph pages with $skip, from what each page kept.
        self.assertEqual([call.kwargs["skip"] for call in self.graph_list.call_args_list], [0, 2, 4])

    def test_a_quiet_account_is_not_crowded_out(self):
        listing = list_all_inbox_messages(limit=2)

        # Gmail's 21 and 19 fill the page; Graph read its own page and keeps its place for the next one.
        self.assertEqual(self.uids(listing), ["21", "g-20"])
        self.assertEqual(listing.cursor, {GRAPH_KEY: "s1", self.imap_key: "u21"})

    def test_an_exhausted_account_is_not_read_again(self):
        cursor = {GRAPH_KEY: "x", self.imap_key: "u15"}

        listing = list_all_inbox_messages(limit=4, cursor=cursor)

        self.assertEqual(self.uids(listing), ["13", "11"])
        self.graph_list.assert_not_called()
        self.assertFalse(listing.has_older)

    def test_each_page_is_cached_under_its_own_key(self):
        list_all_inbox_messages(limit=4, cursor={GRAPH_KEY: "s2", self.imap_key: "u17"})
        list_all_inbox_messages(limit=4, cursor={GRAPH_KEY: "s2", self.imap_key: "u17"})

        self.assertEqual(self.graph_list.call_count, 1)
        self.assertEqual(len(self.imap.opened), 1)
        self.assertIsNotNone(cache.get(f"{INBOX_LIST_CACHE_KEY}:{GRAPH_KEY}:INBOX:4:s2"))
        self.assertIsNotNone(cache.get(f"{INBOX_LIST_CACHE_KEY}:{self.imap_key}:INBOX:4:u17"))

    def test_a_held_back_account_keeps_its_position(self):
        self.imap.answer(self.imap_key, error=InboxBusy("Gmail is busy; try again in about 30 seconds.", 30))

        listing = list_all_inbox_messages(limit=2, cursor={self.imap_key: "u19"})

        self.assertEqual(self.uids(listing), ["g-20", "g-18"])
        self.assertEqual(listing.cursor, {GRAPH_KEY: "s2", self.imap_key: "u19"})

    def test_a_failing_account_keeps_its_position_too(self):
        self.graph_list.side_effect = GraphReadError("Graph refused the read.")

        listing = list_all_inbox_messages(limit=2, cursor={GRAPH_KEY: "s4"})

        self.assertEqual(listing.cursor[GRAPH_KEY], "s4")
        self.assertTrue(listing.has_older)

    def test_one_account_pages_by_its_own_cursor(self):
        first = list_inbox_messages(limit=4, account=self.imap_key)
        older = list_inbox_messages(limit=4, account=self.imap_key, cursor={self.imap_key: "u15"})

        self.assertEqual([row["uid"] for row in first], ["21", "19", "17", "15"])
        self.assertEqual([row["uid"] for row in older], ["13", "11"])
        self.assertEqual(list_inbox_messages(limit=4, account=self.imap_key, cursor={self.imap_key: "x"}), [])
        self.assertEqual(paging.decode(paging.encode({self.imap_key: "u15"})), {self.imap_key: "u15"})
