from datetime import timedelta

from django.contrib.admin.models import LogEntry

from apps.core.models import EmailMonitorState
from apps.core.services.email.bounces import state
from apps.core.tests.services.email_monitoring.bounce_scan.test_bounce_rescan import STATE_LOGGER, StateTestCase

from ..helpers import SENDER, monitoring_settings
from .test_bounce_scanner import FakeReader


class RescanSinceTests(StateTestCase):
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
