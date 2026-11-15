from datetime import timedelta

from django.contrib.admin.models import LogEntry

from apps.core.models import EmailMonitorState
from apps.core.services.email.bounces import state
from apps.core.tests.services.email_monitoring.bounce_scan.test_bounce_rescan import StateTestCase

from ..helpers import SENDER, monitoring_settings
from .test_bounce_scanner import FakeReader


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
