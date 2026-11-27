"""``inbox.polling``: the background poll that records every inbox account's newest Inbox messages and whether it
connected, reading Gmail IMAP incrementally."""

from django.core.cache import cache
from django.utils import timezone

from apps.core.services.email.graph.mailbox import GraphReadError
from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import health
from apps.mail.services.inbox.reading.accounts import ACCOUNTS_CACHE_KEY
from apps.mail.services.inbox.reading.connection import InboxError
from apps.mail.services.inbox.reading.imap_list import LIST_PARTS
from apps.mail.tests.services.delivery.graph_inbox.helpers import MAILBOX
from apps.mail.tests.services.inbox.accounts.helpers import (
    GRAPH_KEY,
    graph_message,
)
from apps.mail.tests.services.inbox.health.polling.helpers import (
    LOGGER,
    FakeMailbox,
    PollCase,
    Status,
)


class PollAccountsTests(PollCase):
    def test_every_account_is_read_and_recorded_with_its_snapshot(self):
        mailbox = self.use_mailbox(FakeMailbox([1, 2], unseen=[2]))

        result = self.poll(graph=[graph_message("g-1", "2026-10-20T12:00:00Z")])

        self.assertEqual(result, {"connected": 2, "failed": 0, "pruned": 0})
        self.assertEqual(self.graph_list.call_args.args[1:], ("INBOX", health.SNAPSHOT_LIMIT))
        graph_row = self.row(GRAPH_KEY)
        self.assertEqual((graph_row.status, graph_row.address, graph_row.unread_count), (Status.OK, MAILBOX, 1))
        self.assertEqual(
            [(m["uid"], m["account"], m["account_address"]) for m in graph_row.messages], [("g-1", GRAPH_KEY, MAILBOX)]
        )
        self.assertIsNotNone(graph_row.snapshot_at)
        imap_row = self.row(self.imap_key)
        self.assertEqual([(m["uid"], m["is_seen"]) for m in imap_row.messages], [("2", False), ("1", True)])
        self.assertEqual(imap_row.messages[0]["account"], self.imap_key)
        self.assertEqual(imap_row.unread_count, 1)
        self.assertEqual(mailbox.opened, [(self.imap_key, "INBOX")])

    def test_imap_fetches_only_the_messages_the_snapshot_lacks(self):
        known = {"uid": "3", "subject": "Known 3", "is_seen": True, "timestamp": 3.0}
        InboxAccountState.objects.create(
            account_key=self.imap_key,
            address="i2g@gmail.com",
            status=Status.OK,
            snapshot_at=timezone.now(),
            messages=[known, {"uid": "2", "subject": "Known 2", "is_seen": False}],
        )
        # Message 1 is deleted between the search and the fetch.
        mailbox = self.use_mailbox(FakeMailbox([1, 2, 3, 4, 5], unseen=[5, 3], deleted=[1]))

        self.poll()

        self.assertEqual(mailbox.searches, ["ALL", "(UNSEEN)"])
        self.assertEqual(mailbox.fetched, [["5", "4", "1"]])
        # Headers and the start of the text only, never marking anything read (BODY.PEEK).
        self.assertEqual(mailbox.fetch_parts, [LIST_PARTS])
        self.assertIn("BODY.PEEK[HEADER]", LIST_PARTS)
        row = self.row(self.imap_key)
        self.assertEqual(
            [(m["uid"], m["subject"], m["is_seen"]) for m in row.messages],
            [("5", "Mail 5", False), ("4", "Mail 4", True), ("3", "Known 3", False), ("2", "Known 2", True)],
        )
        self.assertEqual(row.unread_count, 2)

    def test_nothing_new_fetches_nothing(self):
        InboxAccountState.objects.create(
            account_key=self.imap_key,
            address="i2g@gmail.com",
            status=Status.OK,
            snapshot_at=timezone.now(),
            messages=[{"uid": "1"}],
        )
        mailbox = self.use_mailbox(FakeMailbox([1]))

        self.poll()

        self.assertEqual(mailbox.fetched, [])
        self.assertEqual([m["uid"] for m in self.row(self.imap_key).messages], ["1"])

    def test_only_the_newest_snapshot_limit_messages_are_kept(self):
        mailbox = self.use_mailbox(FakeMailbox(range(1, health.SNAPSHOT_LIMIT + 6)))

        self.poll()

        self.assertEqual(len(mailbox.fetched[0]), health.SNAPSHOT_LIMIT)
        uids = [m["uid"] for m in self.row(self.imap_key).messages]
        self.assertEqual((uids[0], uids[-1], len(uids)), (str(health.SNAPSHOT_LIMIT + 5), "6", health.SNAPSHOT_LIMIT))

    def test_a_failing_account_is_marked_unreachable_and_the_next_is_still_read(self):
        self.use_mailbox(FakeMailbox([1]))

        with self.assertLogs(LOGGER, "WARNING"):
            result = self.poll(graph=GraphReadError("Graph refused the read."))

        self.assertEqual((result["connected"], result["failed"]), (1, 1))
        self.assertEqual(self.row(GRAPH_KEY).status, Status.UNREACHABLE)
        self.assertEqual(self.row(GRAPH_KEY).consecutive_failures, 1)
        self.assertEqual(self.row(self.imap_key).status, Status.OK)

    def test_an_unexpected_failure_is_logged_and_recorded(self):
        self.use_mailbox(FakeMailbox([1]))

        with self.assertLogs(LOGGER, "ERROR"):
            result = self.poll(graph=RuntimeError("boom"))

        self.assertEqual(result["failed"], 1)
        self.assertEqual(self.row(GRAPH_KEY).detail, health.UNREACHABLE_DETAIL)

    def test_an_imap_session_failure_is_an_inbox_error(self):
        mailbox = self.use_mailbox(FakeMailbox([1]))

        def reset(criteria):
            raise OSError("connection reset")

        mailbox.uids = reset

        with self.assertLogs(LOGGER, "WARNING") as logs:
            result = self.poll()

        self.assertEqual(result, {"connected": 1, "failed": 1, "pruned": 0})
        self.assertIn("Failed to poll the inbox.", logs.output[0])
        self.assertEqual(self.row(self.imap_key).status, Status.UNREACHABLE)

    def test_an_inbox_error_from_the_session_is_kept(self):
        self.open_inbox.side_effect = InboxError("That Gmail account is not available in the Inbox.")

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.poll()

        self.assertIn("not available in the Inbox", logs.output[0])

    def test_states_of_accounts_no_longer_read_are_pruned(self):
        InboxAccountState.objects.create(account_key="imap:gone", messages=[{"uid": "1", "subject": "Private"}])
        self.use_mailbox(FakeMailbox([]))

        result = self.poll()

        self.assertEqual(result["pruned"], 1)
        self.assertEqual(
            set(InboxAccountState.objects.values_list("account_key", flat=True)), {GRAPH_KEY, self.imap_key}
        )

    def test_the_account_list_is_read_afresh(self):
        self.use_mailbox(FakeMailbox([]))
        # A stale cached list (another container saved the configuration) is not trusted by the poller.
        cache.set(ACCOUNTS_CACHE_KEY, [], 60)

        result = self.poll()

        self.assertEqual(result["connected"], 2)

    def test_a_stop_request_ends_the_poll(self):
        result = self.poll(should_stop=lambda: True)

        self.assertEqual((result["connected"], result["failed"]), (0, 0))
        self.graph_list.assert_not_called()
        self.open_inbox.assert_not_called()
