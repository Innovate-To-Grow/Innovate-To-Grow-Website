"""SMS quiet hours: the window (overnight or not), when it ends (by local wall time, across a daylight-saving
change), and the switches that turn it off."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings

from apps.mail.services.sms import quiet_hours
from apps.mail.services.sms.quiet_hours import QuietWindow

from .policy_helpers import DAYTIME, QUIET_ENDS, QUIET_MOMENT, sms_settings

PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific(*args):
    return datetime(*args, tzinfo=PACIFIC)


class QuietWindowTests(SimpleTestCase):
    overnight = QuietWindow(start=time(20, 0), end=time(9, 0), zone=PACIFIC)
    midday = QuietWindow(start=time(12, 0), end=time(13, 30), zone=PACIFIC)

    def test_an_overnight_window_spans_midnight(self):
        for moment, inside in (
            (pacific(2026, 11, 11, 19, 59), False),
            (pacific(2026, 11, 11, 20, 0), True),
            (pacific(2026, 11, 11, 23, 59), True),
            (pacific(2026, 11, 12, 0, 0), True),
            (pacific(2026, 11, 12, 8, 59), True),
            (pacific(2026, 11, 12, 9, 0), False),
        ):
            with self.subTest(moment=moment):
                self.assertEqual(self.overnight.contains(moment), inside)

    def test_an_overnight_window_ends_the_next_morning_or_this_morning(self):
        self.assertEqual(self.overnight.ends_after(pacific(2026, 11, 11, 22, 0)), pacific(2026, 11, 12, 9, 0))
        self.assertEqual(self.overnight.ends_after(pacific(2026, 11, 12, 3, 0)), pacific(2026, 11, 12, 9, 0))

    def test_a_daytime_window_ends_the_same_day(self):
        self.assertTrue(self.midday.contains(pacific(2026, 11, 11, 12, 30)))
        self.assertFalse(self.midday.contains(pacific(2026, 11, 11, 13, 30)))
        self.assertEqual(self.midday.ends_after(pacific(2026, 11, 11, 12, 30)), pacific(2026, 11, 11, 13, 30))

    def test_the_end_is_local_wall_time_across_a_daylight_saving_change(self):
        # Clocks went back at 02:00 on 2026-11-01: the window that began at 20:00 PDT ends at 09:00 PST.
        end = self.overnight.ends_after(pacific(2026, 10, 31, 21, 0))
        self.assertEqual(end.astimezone(UTC), datetime(2026, 11, 1, 17, 0, tzinfo=UTC))
        self.assertEqual(self.overnight.label(), "20:00–09:00 America/Los_Angeles")

    def test_a_moment_in_another_zone_is_compared_in_the_windows_zone(self):
        self.assertTrue(self.overnight.contains(datetime(2026, 11, 12, 7, 30, tzinfo=UTC)))


@override_settings(SMS_QUIET_HOURS_ENFORCED=True)
class HeldUntilTests(TestCase):
    def test_inside_the_default_window_texts_wait_for_its_end(self):
        self.assertEqual(quiet_hours.held_until(QUIET_MOMENT), QUIET_ENDS)
        self.assertEqual(quiet_hours.next_send_time(QUIET_MOMENT), QUIET_ENDS)

    def test_outside_it_they_go_now(self):
        self.assertIsNone(quiet_hours.held_until(DAYTIME))
        self.assertEqual(quiet_hours.next_send_time(DAYTIME), DAYTIME)

    def test_staff_can_turn_them_off_or_move_them(self):
        sms_settings(quiet_hours_enabled=False)
        self.assertIsNone(quiet_hours.held_until(QUIET_MOMENT))
        sms_settings(quiet_hours_enabled=True, quiet_hours_start=time(11, 0), quiet_hours_end=time(13, 0))
        self.assertEqual(quiet_hours.held_until(DAYTIME), datetime(2026, 11, 11, 21, 0, tzinfo=UTC))

    def test_a_window_that_ends_when_it_starts_holds_nothing(self):
        config = sms_settings()
        config.quiet_hours_end = config.quiet_hours_start
        self.assertIsNone(quiet_hours.quiet_window(config))


class TestRunSwitchTests(TestCase):
    def test_test_runs_never_hold_texts(self):
        # The test settings switch quiet hours off, so no test depends on the time of day it runs.
        self.assertIsNone(quiet_hours.held_until(QUIET_MOMENT))

    @override_settings(SMS_QUIET_HOURS_ENFORCED=True)
    def test_every_deployment_enforces_them(self):
        from config.settings.base.integrations import sms as sms_settings_module

        self.assertTrue(sms_settings_module.SMS_QUIET_HOURS_ENFORCED)
        self.assertIsNotNone(quiet_hours.quiet_window())
