"""The inbox lists from the poller's snapshot while it is fresh, records the outcome of every live read, and leaves
out the accounts that could not connect recently (``messages`` + ``health``)."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.services.email.graph.mailbox import GraphReadError
from apps.mail.models import InboxAccountState
from apps.mail.services.inbox import health
from apps.mail.services.inbox.accounts import readable_accounts
from apps.mail.services.inbox.connection import INBOX_LIST_CACHE_KEY, InboxBusy, InboxError
from apps.mail.services.inbox.messages import fetch_inbox_message, list_all_inbox_messages, list_inbox_messages
from apps.mail.tests.services.delivery.graph_inbox.test_graph_inbox_backend import MAILBOX, graph_config
from apps.mail.tests.services.inbox.accounts.helpers import (
    GRAPH_KEY,
    LIST_TARGET,
    UniversalInboxMixin,
    gmail_account,
    graph_message,
    imap_message,
)

Status = InboxAccountState.Status
GRAPH_MESSAGES = [graph_message("g-20", "2026-10-20T12:00:00Z")]


def snapshot_message(uid, account_key, address, timestamp=1.0, **overrides):
    return {
        "uid": uid,
        "subject": f"Snapshot {uid}",
        "timestamp": timestamp,
        "is_seen": False,
        "account": account_key,
        "account_address": address,
    } | overrides


class SnapshotCase(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"
        self.imap.answer(self.imap_key, [imap_message("i-21", 21), imap_message("i-19", 19)])
        self.now = timezone.now()

    def state(self, key, **fields):
        """A state recorded for the mailbox ``key`` reads now (unless ``address`` says otherwise)."""
        fields.setdefault("address", MAILBOX if key == GRAPH_KEY else "i2g@gmail.com")
        return InboxAccountState.objects.create(account_key=key, **fields)

    def fresh(self, key, address, uids, **fields):
        return self.state(
            key,
            address=address,
            status=Status.OK,
            snapshot_at=self.now,
            messages=[snapshot_message(uid, key, address) for uid in uids],
            **fields,
        )

    def row(self, key):
        return InboxAccountState.objects.get(account_key=key)


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


class LiveReadHealthTests(SnapshotCase):
    def test_a_read_of_the_snapshot_size_also_refreshes_the_snapshot(self):
        list_inbox_messages(limit=50, account=self.imap_key)

        row = self.row(self.imap_key)
        self.assertEqual((row.status, row.address, row.consecutive_failures), (Status.OK, "i2g@gmail.com", 0))
        self.assertEqual([message["uid"] for message in row.messages], ["i-21", "i-19"])
        self.assertEqual(row.messages[0]["account"], self.imap_key)
        self.assertEqual(row.unread_count, 2)
        self.assertIsNotNone(row.snapshot_at)

    def test_a_smaller_read_records_the_connection_only(self):
        list_inbox_messages(limit=30, account=self.imap_key)

        row = self.row(self.imap_key)
        self.assertEqual(row.status, Status.OK)
        self.assertIsNone(row.snapshot_at)

    def test_a_sent_read_never_replaces_the_inbox_snapshot(self):
        list_inbox_messages(limit=50, account=self.imap_key, folder="SENT")

        self.assertIsNone(self.row(self.imap_key).snapshot_at)

    def test_a_failed_imap_read_marks_the_account_unreachable(self):
        self.imap.answer(self.imap_key, error=InboxError("IMAP login failed."))

        with self.assertRaises(InboxError):
            list_inbox_messages(limit=30, account=self.imap_key)

        row = self.row(self.imap_key)
        self.assertEqual((row.status, row.detail), (Status.UNREACHABLE, health.UNREACHABLE_DETAIL))

    def test_a_failed_graph_read_marks_the_account_unreachable(self):
        with (
            patch(LIST_TARGET, autospec=True, side_effect=GraphReadError("Graph refused the read.")),
            self.assertRaises(InboxError),
        ):
            list_inbox_messages(limit=30, account=GRAPH_KEY)

        self.assertEqual(self.row(GRAPH_KEY).status, Status.UNREACHABLE)

    def test_an_unexpected_failure_is_recorded_and_raised(self):
        with patch(LIST_TARGET, autospec=True, side_effect=RuntimeError("boom")), self.assertRaises(RuntimeError):
            list_inbox_messages(limit=30, account=GRAPH_KEY)

        self.assertEqual(self.row(GRAPH_KEY).status, Status.UNREACHABLE)

    def test_a_held_back_read_is_busy_and_falls_back_to_the_last_snapshot(self):
        self.state(
            self.imap_key,
            status=Status.OK,
            snapshot_at=self.now - timedelta(days=1),
            messages=[snapshot_message("old", self.imap_key, "i2g@gmail.com")],
        )
        self.imap.answer(self.imap_key, error=InboxBusy("Gmail is busy; try again in about 30 seconds.", 30))

        with self.assertRaises(InboxBusy) as raised:
            list_inbox_messages(limit=30, account=self.imap_key)

        self.assertEqual([message["uid"] for message in raised.exception.stale], ["old"])
        self.assertEqual(self.row(self.imap_key).status, Status.BUSY)

    def test_a_held_back_sent_read_has_no_snapshot_to_fall_back_to(self):
        self.state(self.imap_key, status=Status.OK, snapshot_at=self.now - timedelta(days=1), messages=[{"uid": "old"}])
        self.imap.answer(self.imap_key, error=InboxBusy("Gmail is busy.", 30))

        with self.assertRaises(InboxBusy) as raised:
            list_inbox_messages(limit=30, account=self.imap_key, folder="SENT")

        self.assertIsNone(raised.exception.stale)

    def test_a_held_back_read_without_any_snapshot_has_nothing_stale(self):
        self.imap.answer(self.imap_key, error=InboxBusy("Gmail is busy.", 30))

        with self.assertRaises(InboxBusy) as raised:
            list_inbox_messages(limit=30, account=self.imap_key)

        self.assertIsNone(raised.exception.stale)

    def test_opening_an_inbox_message_marks_it_read_in_the_snapshot(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["42", "43"], unread_count=2)
        self.imap.answer(self.imap_key, [imap_message("42", 21)])

        fetch_inbox_message("42", account=self.imap_key)

        row = self.row(self.imap_key)
        self.assertEqual([message["is_seen"] for message in row.messages], [True, False])
        self.assertEqual(row.unread_count, 1)

    def test_opening_a_sent_message_leaves_the_snapshot_alone(self):
        self.fresh(self.imap_key, "i2g@gmail.com", ["42"], unread_count=1)
        self.imap.answer(self.imap_key, [imap_message("42", 21)])

        fetch_inbox_message("42", folder="SENT", account=self.imap_key)

        self.assertEqual(self.row(self.imap_key).unread_count, 1)


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
