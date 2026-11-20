"""The inbox lists from the poller's snapshot while it is fresh and leaves out the accounts that could not
connect recently (``messages`` + ``health``)."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import health
from apps.mail.services.inbox.reading.accounts import readable_accounts
from apps.mail.services.inbox.reading.connection import INBOX_LIST_CACHE_KEY
from apps.mail.services.inbox.reading.listing import list_all_inbox_messages, list_inbox_messages
from apps.mail.tests.services.delivery.graph_inbox.helpers import MAILBOX
from apps.mail.tests.services.inbox.accounts.helpers import (
    GRAPH_KEY,
    LIST_TARGET,
)
from apps.mail.tests.services.inbox.health.snapshots.helpers import (
    GRAPH_MESSAGES,
    SnapshotCase,
    Status,
)


class SnapshotServedTests(SnapshotCase):
    def test_a_fresh_imap_snapshot_is_listed_without_connecting(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["s-1", "s-2", "s-3"])

        results = list_inbox_messages(limit=15, account=self.imap_key)

        self.open_inbox.assert_not_called()
        self.assertEqual([message["uid"] for message in results], ["s-1", "s-2", "s-3"])
        self.assertEqual(cache.get(f"{INBOX_LIST_CACHE_KEY}:{self.imap_key}:INBOX:15"), results)

    def test_a_fresh_graph_snapshot_is_listed_without_reading_graph(self):
        self.fresh(GRAPH_KEY, MAILBOX, ["s-1"])

        with patch(LIST_TARGET) as graph_list:
            results = list_inbox_messages(limit=30, account=GRAPH_KEY)

        graph_list.assert_not_called()
        self.assertEqual([message["uid"] for message in results], ["s-1"])

    def test_force_refresh_reads_live_and_records_it(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["s-1"])

        results = list_inbox_messages(limit=30, account=self.imap_key, force_refresh=True)

        self.assertEqual(self.imap.opened, [self.imap_key])
        self.assertEqual([message["uid"] for message in results], ["i-21", "i-19"])
        # A list smaller than the snapshot records the connection, not a new snapshot.
        row = self.row(self.imap_key)
        self.assertEqual(row.status, Status.OK)
        self.assertEqual([message["uid"] for message in row.messages], ["s-1"])

    def test_a_stale_snapshot_reads_live(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["s-1"])
        InboxAccountState.objects.update(snapshot_at=self.now - timedelta(hours=1))

        results = list_inbox_messages(limit=30, account=self.imap_key)

        self.assertEqual(self.imap.opened, [self.imap_key])
        self.assertEqual(results[0]["uid"], "i-21")

    def test_the_largest_list_is_never_served_from_the_snapshot(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["s-1"])

        list_inbox_messages(limit=100, account=self.imap_key)

        self.assertEqual(self.imap.opened, [self.imap_key])

    def test_the_sent_folder_and_a_mailbox_override_never_use_the_snapshot(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["s-1"])

        list_inbox_messages(limit=30, account=self.imap_key, folder="SENT")
        list_inbox_messages(limit=30, account=self.imap_key, mailbox="other@gmail.com")

        self.assertEqual(self.imap.opened, [self.imap_key, self.imap_key])


class HiddenAccountListingTests(SnapshotCase):
    def unreachable(self, key, address):
        return self.state(key, address=address, status=Status.UNREACHABLE, checked_at=self.now)

    def test_an_account_that_could_not_connect_recently_is_left_out_and_named(self):
        self.unreachable(self.imap_key, "i2g@gmail.com")

        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES):
            listing = list_all_inbox_messages(limit=30)

        self.open_inbox.assert_not_called()
        self.assertEqual(listing.hidden, ["i2g@gmail.com"])
        self.assertEqual([message["uid"] for message in listing.messages], ["g-20"])
        self.assertEqual(listing.unavailable, [])

    def test_force_refresh_tries_it_again(self):
        self.unreachable(self.imap_key, "i2g@gmail.com")

        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES):
            listing = list_all_inbox_messages(limit=30, force_refresh=True)

        self.assertEqual(self.imap.opened, [self.imap_key])
        self.assertEqual(listing.hidden, [])
        self.assertEqual([message["uid"] for message in listing.messages], ["i-21", "g-20", "i-19"])
        # It connected: shown again from now on.
        self.assertEqual(self.row(self.imap_key).status, Status.OK)
        self.assertEqual(health.hidden_keys(readable_accounts()), set())

    def test_when_every_account_is_hidden_they_are_all_tried(self):
        self.unreachable(self.imap_key, "i2g@gmail.com")
        self.unreachable(GRAPH_KEY, MAILBOX)

        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES) as graph_list:
            listing = list_all_inbox_messages(limit=30)

        graph_list.assert_called_once()
        self.assertEqual(self.imap.opened, [self.imap_key])
        self.assertEqual(listing.hidden, [])
        self.assertEqual(len(listing.messages), 3)

    def test_fresh_snapshots_are_merged_without_connecting(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["s-1"])
        self.fresh(GRAPH_KEY, MAILBOX, ["s-2"])

        with patch(LIST_TARGET) as graph_list:
            listing = list_all_inbox_messages(limit=30)

        graph_list.assert_not_called()
        self.open_inbox.assert_not_called()
        self.assertEqual(sorted(message["uid"] for message in listing.messages), ["s-1", "s-2"])
