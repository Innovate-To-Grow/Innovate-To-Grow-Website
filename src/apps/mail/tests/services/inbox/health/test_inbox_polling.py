"""``inbox.polling``: the background poll that records every inbox account's newest Inbox messages and whether it
connected, reading Gmail IMAP incrementally, and the job chain that runs it."""

import re
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import registered_job_kinds
from apps.core.services.email.graph.mailbox import GraphReadError
from apps.mail.models import InboxAccountState
from apps.mail.services.inbox import health, polling
from apps.mail.services.inbox.accounts import ACCOUNTS_CACHE_KEY
from apps.mail.services.inbox.connection import InboxBusy, InboxError
from apps.mail.services.inbox.messages import list_inbox_messages
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
LOGGER = "apps.mail.services.inbox.polling"


class FakeMailbox:
    """An IMAP session over ``messages`` (uid -> message): ``uids`` answers the two searches the poller runs,
    ``fetch`` returns the requested uids that still exist, and ``fetch("ALL")`` answers a live list read."""

    def __init__(self, uids, *, unseen=(), deleted=()):
        self.messages = {str(uid): imap_message(str(uid), 1 + int(uid) % 28, subject=f"Mail {uid}") for uid in uids}
        self.unseen = {str(uid) for uid in unseen}
        self.deleted = {str(uid) for uid in deleted}
        self.searches, self.fetched, self.fetch_kwargs = [], [], []
        self.opened = []

    def uids(self, criteria):
        self.searches.append(str(criteria))
        if criteria == "ALL":
            return sorted(self.messages, key=int)
        return sorted(self.unseen, key=int)

    def fetch(self, criteria, *, limit=None, reverse=False, **kwargs):
        if criteria == "ALL":
            # The inbox's own live list read (``messages._read_list``), not the poller's.
            present = [uid for uid in sorted(self.messages, key=int) if uid not in self.deleted]
            return [self.messages[uid] for uid in (present[::-1] if reverse else present)][:limit]
        requested = re.fullmatch(r"\(UID ([\d,]+)\)", str(criteria)).group(1).split(",")
        self.fetched.append(requested)
        self.fetch_kwargs.append(kwargs)
        return [self.messages[uid] for uid in requested if uid not in self.deleted]

    @contextmanager
    def __call__(self, mailbox=None, folder="INBOX", *, account=None):
        self.opened.append((account.key, folder))
        yield self


class PollCase(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"

    def use_mailbox(self, mailbox):
        self.open_inbox.side_effect = mailbox
        return mailbox

    def row(self, key):
        return InboxAccountState.objects.get(account_key=key)

    def poll(self, graph=None, **kwargs):
        graph_kwargs = {"side_effect": graph} if isinstance(graph, BaseException) else {"return_value": graph or []}
        with patch(LIST_TARGET, autospec=True, **graph_kwargs) as graph_list:
            result = polling.poll_accounts(**kwargs)
        self.graph_list = graph_list
        return result


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
        self.assertEqual(mailbox.fetch_kwargs, [{"mark_seen": False, "bulk": True}])
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


class ChangedMailboxTests(PollCase):
    """An IMAP account's key is its row (``imap:<pk>``), so when staff point the row at another mailbox (a new Gmail
    username) the key stays the same. The old mailbox's snapshot must never be listed under the new address, and the
    incremental poll must not reuse its summaries for uids the two mailboxes share (IMAP uids restart at 1 in every
    mailbox): ``health.states_for`` ignores a state recorded for another address."""

    def setUp(self):
        super().setUp()
        InboxAccountState.objects.create(
            account_key=self.imap_key,
            address="i2g@gmail.com",
            status=Status.OK,
            snapshot_at=timezone.now(),
            messages=[{"uid": "1", "subject": "Old mailbox private subject", "is_seen": True}],
        )
        self.gmail.gmail_username = "someone-else@gmail.com"
        self.gmail.save()

    def test_the_new_mailbox_is_not_listed_with_the_old_ones_mail(self):
        self.use_mailbox(FakeMailbox([1]))

        subjects = [m["subject"] for m in list_inbox_messages(limit=30, account=self.imap_key)]

        self.assertNotIn("Old mailbox private subject", subjects)

    def test_the_poll_does_not_reuse_the_old_mailboxs_summaries(self):
        self.use_mailbox(FakeMailbox([1]))

        self.poll()

        self.assertEqual([m["subject"] for m in self.row(self.imap_key).messages], ["Mail 1"])
        self.assertEqual(self.row(self.imap_key).address, "someone-else@gmail.com")

    # ``record_ok`` without messages and ``record_failure`` write the new address; they must drop the old snapshot.
    def test_a_smaller_live_read_does_not_adopt_the_old_snapshot(self):
        self.use_mailbox(FakeMailbox([1]))
        # A list smaller than the snapshot records the connection only (``record_ok`` without messages) ...
        list_inbox_messages(limit=30, account=self.imap_key)

        # ... after which a list the snapshot could serve must still not show the old mailbox's mail.
        subjects = [m["subject"] for m in list_inbox_messages(limit=15, account=self.imap_key)]

        self.assertNotIn("Old mailbox private subject", subjects)

    def test_a_held_back_read_does_not_fall_back_to_the_old_snapshot(self):
        self.open_inbox.side_effect = InboxBusy("Gmail is busy; try again in about 30 seconds.", 30)

        with self.assertRaises(InboxBusy) as raised:
            list_inbox_messages(limit=30, account=self.imap_key)

        self.assertIsNone(raised.exception.stale)


class PollJobTests(TestCase):
    def jobs(self):
        return BackgroundJob.objects.filter(kind=polling.POLL_JOB_KIND)

    def test_the_kind_is_registered(self):
        self.assertEqual(
            registered_job_kinds()[polling.POLL_JOB_KIND].handler, "apps.mail.services.inbox.polling.run_poll_job"
        )

    def test_maintenance_queues_one_poll(self):
        self.assertTrue(polling.ensure_scheduled())
        self.assertFalse(polling.ensure_scheduled())

        job = self.jobs().get()
        self.assertEqual((job.status, job.max_attempts, job.payload), ("pending", 1, {"requested": "scheduled"}))

    def test_a_running_or_retrying_poll_counts_as_scheduled(self):
        for status in (BackgroundJob.Status.PROCESSING, BackgroundJob.Status.RETRY):
            with self.subTest(status=status):
                BackgroundJob.objects.all().delete()
                BackgroundJob.objects.create(kind=polling.POLL_JOB_KIND, dedupe_key="running", status=status)

                self.assertFalse(polling.ensure_scheduled())
                self.assertEqual(self.jobs().count(), 1)

    def test_a_finished_poll_does_not_count(self):
        BackgroundJob.objects.create(kind=polling.POLL_JOB_KIND, dedupe_key="done", status="succeeded")

        self.assertTrue(polling.ensure_scheduled())
        self.assertEqual(self.jobs().filter(status="pending").count(), 1)

    @override_settings(MAIL_INBOX_POLL_SECONDS=0)
    def test_switched_off_nothing_is_queued(self):
        self.assertFalse(polling.enabled())
        self.assertFalse(polling.ensure_scheduled())
        with patch.object(polling, "poll_accounts") as poll:
            polling.run_poll_job(job=None)

        poll.assert_called_once_with()
        self.assertFalse(self.jobs().exists())

    def test_a_poll_queues_the_next_one_an_interval_later(self):
        before = timezone.now()
        with patch.object(polling, "poll_accounts", return_value={}):
            polling.run_poll_job(job=None)

        job = self.jobs().get()
        self.assertGreaterEqual(job.available_at, before + timedelta(seconds=health.poll_interval_seconds()))
        self.assertLessEqual(job.available_at, timezone.now() + timedelta(seconds=health.poll_interval_seconds()))

    @override_settings(MAIL_INBOX_POLL_SECONDS=600)
    def test_the_next_poll_follows_the_setting(self):
        before = timezone.now()
        with patch.object(polling, "poll_accounts", return_value={}):
            polling.run_poll_job(job=None)

        self.assertGreaterEqual(self.jobs().get().available_at, before + timedelta(seconds=600))

    def test_a_failing_poll_still_queues_the_next_one(self):
        with patch.object(polling, "poll_accounts", side_effect=InboxError("no tables")), self.assertRaises(InboxError):
            polling.run_poll_job(job=None)

        self.assertEqual(self.jobs().filter(status="pending").count(), 1)

    def test_no_second_poll_is_queued_while_one_waits(self):
        polling.ensure_scheduled()
        with patch.object(polling, "poll_accounts", return_value={}):
            polling.run_poll_job(job=None)

        self.assertEqual(self.jobs().count(), 1)

    def test_finished_polls_older_than_a_day_are_purged(self):
        now = timezone.now()
        old, recent = now - timedelta(days=1, minutes=1), now - timedelta(hours=23)
        for index, (status, completed) in enumerate(
            (("succeeded", old), ("failed", old), ("cancelled", old), ("succeeded", recent), ("pending", None))
        ):
            BackgroundJob.objects.create(
                kind=polling.POLL_JOB_KIND, dedupe_key=f"job-{index}", status=status, completed_at=completed
            )
        BackgroundJob.objects.create(kind="other.kind", dedupe_key="other", status="succeeded", completed_at=old)

        self.assertEqual(polling.purge_finished_jobs(now=now), 3)
        self.assertEqual(sorted(self.jobs().values_list("dedupe_key", flat=True)), ["job-3", "job-4"])
        self.assertTrue(BackgroundJob.objects.filter(kind="other.kind").exists())
