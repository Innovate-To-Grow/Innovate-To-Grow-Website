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

from .helpers import SENDER, make_email, monitoring_settings
from .ndr_samples import ORIGINAL_ID, exchange_ndr
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

    def test_without_an_actor_it_is_logged_but_leaves_no_admin_history(self):
        with self.assertLogs(STATE_LOGGER, "INFO") as logs:
            result = state.rescan_since(SENDER, self.now - timedelta(days=1), now=self.now)

        self.assertEqual(result.status, "moved")
        self.assertIn("actor=-", logs.output[0])
        self.assertFalse(LogEntry.objects.exists())

    def test_the_earliest_allowed_time_is_accepted_and_a_second_earlier_is_not(self):
        with monitoring_settings(bounce_max_lookback_days=30):
            too_early = state.rescan_since(SENDER, self.now - timedelta(days=30, seconds=1), now=self.now)
            edge = state.rescan_since(SENDER, self.now - timedelta(days=30), now=self.now)

        self.assertEqual((too_early.status, too_early.earliest), ("too_early", self.now - timedelta(days=30)))
        self.assertEqual(edge.status, "moved")
        self.assertEqual(self.row().checkpoint_at, self.now - timedelta(days=30))

    def test_a_time_in_the_future_is_refused(self):
        result = state.rescan_since(SENDER, self.now + timedelta(minutes=1), actor=self.staff, now=self.now)

        self.assertEqual(result.status, "future")
        self.assertEqual(self.row().checkpoint_at, self.checkpoint)
        self.assertFalse(LogEntry.objects.exists())

    def test_the_longest_lookback_never_reaches_past_the_bounce_retention(self):
        with monitoring_settings(bounce_max_lookback_days=90, bounce_retention_days=30):
            self.assertEqual(state.max_lookback_days(), 30)
            result = state.rescan_since(SENDER, self.now - timedelta(days=31), now=self.now)

        self.assertEqual((result.status, result.earliest), ("too_early", self.now - timedelta(days=30)))
        self.assertEqual(self.row().checkpoint_at, self.checkpoint)

    def test_a_time_not_before_the_checkpoint_changes_nothing(self):
        for since in (self.checkpoint, self.checkpoint + timedelta(minutes=1)):
            with self.subTest(since=since):
                result = state.rescan_since(SENDER, since, actor=self.staff, now=self.now)

                self.assertEqual((result.status, result.previous), ("not_earlier", self.checkpoint))
        self.assertEqual(self.row().checkpoint_at, self.checkpoint)
        self.assertFalse(LogEntry.objects.exists())

    def test_a_running_scan_keeps_its_lease_and_saves_its_own_checkpoint(self):
        token = state.acquire_lease(SENDER, self.now)

        result = state.rescan_since(SENDER, self.now - timedelta(days=2), actor=self.staff, now=self.now)

        self.assertEqual(result.status, "running")
        self.assertEqual(result.lease_until, self.row().lease_until)
        self.assertEqual((self.row().lease_token, self.row().checkpoint_at), (token, self.checkpoint))
        self.assertFalse(LogEntry.objects.exists())
        state.finish(SENDER, token, checkpoint=self.now, stats={})
        self.assertEqual(self.row().checkpoint_at, self.now)

    def test_an_expired_lease_is_released_so_the_scan_that_held_it_saves_nothing(self):
        token = state.acquire_lease(SENDER, self.now - timedelta(hours=2))

        result = state.rescan_since(SENDER, self.now - timedelta(days=2), now=self.now)
        state.finish(SENDER, token, checkpoint=self.now, stats={"listed": 9})

        self.assertEqual(result.status, "moved")
        row = self.row()
        self.assertEqual(row.checkpoint_at, self.now - timedelta(days=2))
        self.assertEqual((row.lease_token, row.lease_until, row.last_run_stats), (None, None, {}))

    def test_a_paused_mailbox_stays_paused_and_is_not_scanned(self):
        state.set_paused(SENDER, True)

        result = state.rescan_since(SENDER, self.now - timedelta(days=2), now=self.now)
        reader = FakeReader([], {})
        outcome = self.scan(reader, self.now)

        self.assertEqual((result.status, result.paused), ("moved", True))
        self.assertTrue(self.row().paused)
        self.assertEqual((outcome.status, reader.since), ("paused", []))

    def test_before_any_scan_the_first_scan_starts_at_the_chosen_time(self):
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=None)
        since = self.now - timedelta(days=10)

        result = state.rescan_since(SENDER, since, now=self.now)
        reader = FakeReader([], {})
        self.scan(reader, self.now)

        self.assertEqual((result.status, result.previous), ("moved", None))
        self.assertEqual(reader.since, [since - timedelta(seconds=900)])

    def test_a_mailbox_without_a_state_row_gets_one(self):
        result = state.rescan_since("other@ucmerced.edu", self.now - timedelta(hours=1), now=self.now)

        self.assertEqual(result.status, "moved")
        moved = EmailMonitorState.objects.get(mailbox="other@ucmerced.edu").checkpoint_at
        self.assertEqual(moved, self.now - timedelta(hours=1))


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


class LookbackTests(StateTestCase):
    def setUp(self):
        super().setUp()
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=None)

    def test_the_default_comes_from_the_settings_and_stays_within_the_bounds(self):
        with monitoring_settings(bounce_initial_lookback_hours=72, bounce_max_lookback_days=90):
            self.assertEqual((state.default_lookback_hours(), state.lookback_bounds()), (72, (1, 2160)))
            self.assertEqual(state.lookback_hours(None), 72)
        with monitoring_settings(bounce_initial_lookback_hours=5000, bounce_max_lookback_days=90):
            self.assertEqual(state.default_lookback_hours(), 2160)
        with monitoring_settings(bounce_initial_lookback_hours=0):
            self.assertEqual(state.default_lookback_hours(), 1)

    def test_staff_set_and_reset_it_and_each_change_is_recorded(self):
        with monitoring_settings(bounce_initial_lookback_hours=72):
            first = state.set_lookback(SENDER, 240, actor=self.staff)
            self.assertEqual(
                (first, self.row().initial_lookback_hours, state.lookback_hours(self.row())), (None, 240, 240)
            )
            second = state.set_lookback(SENDER, None, actor=self.staff)
            self.assertEqual(
                (second, self.row().initial_lookback_hours, state.lookback_hours(self.row())), (240, None, 72)
            )

        history = list(LogEntry.objects.order_by("action_time").values_list("change_message", flat=True))
        self.assertEqual(
            history, ["First-scan lookback: default (72 h) → 240 h.", "First-scan lookback: 240 h → default (72 h)."]
        )

    def test_an_unchanged_value_records_nothing(self):
        state.set_lookback(SENDER, None, actor=self.staff)
        state.set_lookback(SENDER, 24, actor=self.staff)
        state.set_lookback(SENDER, 24, actor=self.staff)

        self.assertEqual(LogEntry.objects.count(), 1)

    def test_values_outside_the_bounds_are_refused(self):
        with monitoring_settings(bounce_max_lookback_days=90):
            for hours in (0, -1, 2161):
                with self.subTest(hours=hours), self.assertRaises(ValueError):
                    state.set_lookback(SENDER, hours, actor=self.staff)

        self.assertIsNone(self.row().initial_lookback_hours)
        self.assertFalse(LogEntry.objects.exists())

    def test_a_stored_value_outside_the_bounds_is_kept_within_them(self):
        with monitoring_settings(bounce_max_lookback_days=90):
            for stored, used in ((10_000, 2160), (0, 1), (36, 36)):
                with self.subTest(stored=stored):
                    EmailMonitorState.objects.filter(mailbox=SENDER).update(initial_lookback_hours=stored)

                    self.assertEqual(state.lookback_hours(self.row()), used)

    def test_the_first_scan_uses_the_mailbox_lookback_and_later_scans_their_checkpoint(self):
        state.set_lookback(SENDER, 240)
        reader = FakeReader([], {})

        self.scan(reader, self.now)
        self.scan(reader, self.now)

        self.assertEqual(reader.since, [self.now - timedelta(hours=240), self.now - timedelta(seconds=900)])

    def test_a_lookback_changed_after_the_first_scan_is_not_used(self):
        reader = FakeReader([], {})
        self.scan(reader, self.now)

        state.set_lookback(SENDER, 1000)
        self.scan(reader, self.now)

        self.assertEqual(reader.since[1], self.now - timedelta(seconds=900))
