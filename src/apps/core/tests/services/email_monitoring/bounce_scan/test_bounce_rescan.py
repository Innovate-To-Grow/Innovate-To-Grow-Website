"""Rescan since and the first-scan lookback (``bounces.state``), and how a scan uses them.

The checkpoint only ever moves back, within the longest lookback, and never under a running scan's lease; reading
the Inbox again records no bounce twice; every change leaves an admin history line and a log line. Microsoft Graph is
never contacted: the scans read a ``FakeReader``.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce, EmailMonitorState
from apps.core.services.email.bounces import scanner, state
from apps.event.tests.helpers import make_admin

from ..helpers import SENDER, make_email, monitoring_settings
from ..ndr_samples import ORIGINAL_ID, exchange_ndr
from .test_bounce_scanner import READER, FakeReader, listed

STATE_LOGGER = "apps.core.services.email.bounces.state"


def stamp(value) -> str:
    """A time as the admin history line shows it."""
    return f"{timezone.localtime(value):%Y-%m-%d %H:%M}"


class StateTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now().replace(microsecond=0)
        self.staff = make_admin(apps=["mail"])
        self.checkpoint = self.now - timedelta(minutes=5)
        state.state_for(SENDER)
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=self.checkpoint)

    def row(self) -> EmailMonitorState:
        return EmailMonitorState.objects.get(mailbox=SENDER)

    def scan(self, reader, now):
        with patch(READER, return_value=(reader, SENDER, "")), monitoring_settings(bounce_scan_overlap_seconds=900):
            return scanner.scan_mailbox(now=now)


class RescanSinceTests(StateTestCase):
    def test_it_moves_the_checkpoint_back_and_records_who_did_it(self):
        since = self.now - timedelta(days=6)

        with self.assertLogs(STATE_LOGGER, "INFO") as logs:
            result = state.rescan_since(SENDER, since, actor=self.staff, now=self.now)

        self.assertEqual((result.status, result.previous, result.paused), ("moved", self.checkpoint, False))
        self.assertEqual(self.row().checkpoint_at, since)
        entry = LogEntry.objects.get()
        self.assertEqual((entry.user_id, entry.action_flag), (self.staff.pk, CHANGE))
        self.assertEqual(entry.object_id, str(self.row().pk))
        self.assertIn(f"Rescan since {stamp(since)}", entry.change_message)
        self.assertIn(f"checkpoint moved back from {stamp(self.checkpoint)}", entry.change_message)
        self.assertIn(f"action=rescan mailbox={SENDER} actor={self.staff.pk}", logs.output[0])


class RescanAndScanTests(StateTestCase):
    """Scan, rescan, scan again: the second pass reads the old mail again and records nothing twice."""

    def setUp(self):
        super().setUp()
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=None)
        make_email(internet_message_id=ORIGINAL_ID, recipient="nobody@example.com")
        self.ndr = listed(
            "ndr-1",
            subject="Undeliverable: Hello",
            sender="postmaster@ucmerced.onmicrosoft.com",
            received=self.now - timedelta(days=2),
        )
        self.reader = FakeReader([self.ndr], {"ndr-1": exchange_ndr()})

    def test_reading_the_inbox_again_records_no_bounce_twice(self):
        first = self.scan(self.reader, self.now)
        state.rescan_since(SENDER, self.now - timedelta(days=5), now=self.now)
        later = self.now + timedelta(minutes=1)

        again = self.scan(self.reader, later)

        self.assertEqual((first.stats["bounces"], again.stats["bounces"]), (1, 0))
        self.assertEqual((again.stats["candidates"], again.stats["already_processed"]), (1, 1))
        self.assertEqual(self.reader.opened, ["ndr-1"])  # never opened a second time
        self.assertEqual(self.reader.since[1], self.now - timedelta(days=5, seconds=900))
        self.assertEqual(EmailBounce.objects.count(), 1)
        self.assertEqual(self.row().checkpoint_at, later)

    def test_a_report_seen_again_under_a_new_graph_id_is_still_stored_once(self):
        # A report moved out of the Inbox and back gets a new Graph id; its own Message-ID still identifies it.
        self.scan(self.reader, self.now)
        state.rescan_since(SENDER, self.now - timedelta(days=5), now=self.now)
        moved = {**self.ndr, "id": "ndr-1-moved"}

        again = self.scan(FakeReader([moved], {"ndr-1-moved": exchange_ndr()}), self.now + timedelta(minutes=1))

        self.assertEqual((again.stats["bounces"], again.stats["duplicates"]), (0, 1))
        self.assertEqual(EmailBounce.objects.count(), 1)

    def test_a_backlog_longer_than_one_scan_is_read_page_by_page_over_several_scans(self):
        # A rescan far back can list more than one scan may read: each scan stops at its page budget with the
        # checkpoint at what it processed, and the next continues from there (less the overlap) until it catches up.
        start = self.now - timedelta(days=5)
        inbox = [
            listed(f"m-{i}", subject="Hello", sender="person@example.com", received=start + timedelta(minutes=20 * i))
            for i in range(7)
        ]
        reader = FakeReader(inbox, {})
        state.rescan_since(SENDER, self.now - timedelta(days=6), now=self.now)

        outcomes, checkpoints = [], []
        with monitoring_settings(bounce_scan_page_size=2, bounce_scan_max_pages=2):
            for _scan in range(4):
                outcomes.append(self.scan(reader, self.now).status)
                checkpoints.append(self.row().checkpoint_at)

        self.assertEqual(outcomes, ["partial", "partial", "partial", "ok"])
        received = [start + timedelta(minutes=20 * i) for i in (2, 4, 6)]
        self.assertEqual(checkpoints, [*received, self.now])
        self.assertEqual(reader.opened, [])  # none of them looked like a report

    def test_a_rescan_saved_just_before_the_scan_takes_the_lease_is_where_it_starts(self):
        # The scan reads its checkpoint once it holds the lease, so a rescan that lands after the scan first looked at
        # the state, but before it took the lease, is neither missed nor overwritten.
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=self.now - timedelta(minutes=1))
        since = self.now - timedelta(days=4)
        take_lease = state.acquire_lease

        def rescan_then_take_lease(mailbox, now):
            state.rescan_since(mailbox, since, now=now)
            return take_lease(mailbox, now)

        with patch.object(state, "acquire_lease", side_effect=rescan_then_take_lease):
            outcome = self.scan(self.reader, self.now)

        self.assertEqual(self.reader.since[0], since - timedelta(seconds=900))
        self.assertEqual((outcome.status, outcome.stats["bounces"]), ("ok", 1))  # the 2-day-old report was read
        self.assertEqual(self.row().checkpoint_at, self.now)

    def test_a_rescan_tried_while_a_scan_runs_is_refused_and_the_scan_ends_as_usual(self):
        attempts = []
        list_messages = self.reader.list_received_since

        def list_and_try_a_rescan(folder, since, limit):
            attempts.append(state.rescan_since(SENDER, self.now - timedelta(days=5), now=self.now))
            return list_messages(folder, since, limit)

        self.reader.list_received_since = list_and_try_a_rescan
        outcome = self.scan(self.reader, self.now)

        self.assertEqual([attempt.status for attempt in attempts], ["running"])
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(self.row().checkpoint_at, self.now)
