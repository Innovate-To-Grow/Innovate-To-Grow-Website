"""Every live inbox read records its outcome in the account's health state (``messages`` + ``health``)."""

from datetime import timedelta
from unittest.mock import patch

from apps.core.services.email.graph.mailbox import GraphReadError
from apps.mail.services.inbox.polling import health
from apps.mail.services.inbox.reading.connection import InboxBusy, InboxError
from apps.mail.services.inbox.reading.listing import list_inbox_messages
from apps.mail.services.inbox.reading.messages import fetch_inbox_message
from apps.mail.tests.services.inbox.accounts.helpers import (
    GRAPH_KEY,
    LIST_TARGET,
    imap_message,
)
from apps.mail.tests.services.inbox.health.snapshots.helpers import (
    SnapshotCase,
    Status,
    snapshot_message,
)


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
