from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.core.models import (
    EmailMonitorState,
)
from apps.core.services.email.bounces import state
from apps.core.services.email.inbound import InboxReader
from apps.core.tests.services.email_monitoring.helpers import SENDER, monitoring_settings
from apps.mail.services.email_monitoring import health
from apps.mail.tests.admin.email_monitoring.bounces.test_bounce_backfill_admin import (
    DISABLED_RESCAN,
    INTAKE_URL,
    READERS,
    BackfillTestCase,
    local_input,
)


class CardTests(BackfillTestCase):
    def test_the_card_offers_both_forms_with_their_bounds(self):
        with monitoring_settings(bounce_max_lookback_days=90, bounce_initial_lookback_hours=72):
            response = self.client.get(self.overview)

        backfill = response.context["health"]["bounces"]["backfill"]
        self.assertEqual(
            (backfill["max_days"], backfill["lookback_min"], backfill["lookback_max"], backfill["lookback_default"]),
            (90, 1, 2160, 72),
        )
        self.assertContains(response, "Read older mail again")
        self.assertContains(response, "Rescan since (America/Los_Angeles)")
        self.assertContains(
            response,
            f'type="datetime-local" name="since" required step="60" min="{backfill["earliest_input"]}" '
            f'max="{backfill["latest_input"]}"',
        )
        self.assertContains(response, 'name="lookback_hours" min="1" max="2160" step="1"')
        self.assertContains(response, 'placeholder="72"')
        self.assertContains(response, "at most 90 days back")
        self.assertContains(response, "now 72 hours (the default). Allowed: 1 to 2,160 hours;")
        self.assertContains(response, "This mailbox already has a checkpoint, so the lookback is not used")
        self.assertNotContains(response, DISABLED_RESCAN)

    def test_a_lookback_set_by_staff_is_shown_as_such(self):
        state.set_lookback(SENDER, 240)

        response = self.client.get(self.overview)

        self.assertContains(response, 'value="240"')
        self.assertContains(response, "now 240 hours (set here)")

    def test_the_earliest_time_offered_is_the_first_whole_minute_allowed(self):
        now = datetime(2026, 11, 11, 12, 0, 30, tzinfo=UTC)

        with monitoring_settings(bounce_max_lookback_days=90, bounce_initial_lookback_hours=72):
            backfill = health.backfill(None, now)

        earliest = now - timedelta(days=90)  # 12:00:30 UTC; the input cannot hold seconds, so 12:01 is offered
        self.assertEqual(backfill["earliest_input"], local_input(earliest.replace(minute=1, second=0)))
        self.assertEqual(backfill["latest_input"], local_input(now))
        self.assertEqual((backfill["lookback_hours"], backfill["lookback_custom"]), (72, False))

    def test_the_last_scan_says_how_many_reports_were_already_recorded(self):
        # After a rescan, reports read again are skipped without being opened: the card counts them.
        stats = {"listed": 40, "candidates": 12, "already_processed": 12, "opened": 0, "bounces": 0, "duplicates": 0}
        EmailMonitorState.objects.filter(mailbox=SENDER).update(last_run_stats=stats)

        response = self.client.get(self.overview)

        self.assertContains(response, "12 bounce candidates (12 already recorded), 0 opened, 0 new bounce records")

    def test_a_running_scan_shows_on_the_card(self):
        state.acquire_lease(SENDER, timezone.now())

        response = self.client.get(self.overview)

        self.assertTrue(response.context["health"]["bounces"]["scan_running"])
        self.assertContains(response, "running now (started")

    def test_a_mailbox_paused_before_its_first_scan_shows_as_paused(self):
        state.set_paused(SENDER, True)  # no scan has finished yet: the row only holds a checkpoint

        response = self.client.get(self.overview)

        self.assertEqual(response.context["health"]["bounces"]["level"], "paused")
        self.assertContains(response, "<strong>Paused</strong>")
        self.assertNotContains(response, "Waiting for the first scan")
        self.assertContains(response, '<input type="hidden" name="action" value="resume">')

    def test_the_rescan_button_is_disabled_when_the_mailbox_cannot_be_read(self):
        self.send_only_scope()

        response = self.client.get(self.overview)

        self.assertContains(response, DISABLED_RESCAN)


class CadenceTests(BackfillTestCase):
    """The card says how often the Inbox is really read: the bounce scan's own cadence, from the code that schedules
    it, and every other app that lists the same Inbox on its own schedule (through core's inbox-reader registry)."""

    def card(self):
        return self.client.get(self.overview)

    def test_the_interval_is_the_one_scans_follow_with_the_catch_up(self):
        with monitoring_settings(bounce_scan_interval_seconds=600):
            response = self.card()

        self.assertEqual(
            (response.context["health"]["bounces"]["every"], response.context["health"]["bounces"]["catch_up"]),
            ("10 min", "2 min"),
        )
        self.assertContains(
            response, "<dt>Interval</dt><dd>every 10 min; every 2 min while catching up</dd>", html=False
        )
        self.assertNotContains(response, " min min")

    def test_an_interval_that_is_not_whole_minutes_is_shown_exactly(self):
        with monitoring_settings(bounce_scan_interval_seconds=90):
            response = self.card()

        # 90 s used to read "every 1 min"; catching up is no sooner than that, so it is not repeated.
        self.assertContains(response, "<dt>Interval</dt><dd>every 90 s</dd>", html=False)

    def test_a_scan_counts_as_recent_against_the_real_interval(self):
        # The interval is never under a minute, so a scan two minutes ago is recent with a 5-second setting.
        EmailMonitorState.objects.filter(mailbox=SENDER).update(
            last_run_finished_at=self.now - timedelta(minutes=2), last_success_at=self.now - timedelta(minutes=2)
        )
        with monitoring_settings(bounce_scan_interval_seconds=5):
            self.assertEqual(health.bounce_processing()["level"], "ok")
        EmailMonitorState.objects.filter(mailbox=SENDER).update(last_success_at=self.now - timedelta(minutes=4))
        with monitoring_settings(bounce_scan_interval_seconds=5):
            self.assertEqual(health.bounce_processing()["level"], "warning")

    def test_other_readers_of_the_inbox_are_listed_with_their_own_cadence(self):
        readers = [
            InboxReader("Helpdesk intake", "paused", 120, INTAKE_URL),
            InboxReader("Another reader", "running", 3600),
        ]
        with patch(READERS, return_value=readers):
            response = self.card()

        self.assertEqual(
            response.context["health"]["bounces"]["other_readers"],
            [
                {"label": "Helpdesk intake", "every": "2 min", "state": "paused", "url": INTAKE_URL},
                {"label": "Another reader", "every": "1 h", "state": "", "url": ""},
            ],
        )
        self.assertContains(response, "This card controls bounce processing only")
        self.assertContains(
            response, f'<a href="{INTAKE_URL}">Helpdesk intake</a>, every 2 min (paused); Another reader, every 1 h.'
        )

    def test_reader_states_are_named_and_no_line_without_other_readers(self):
        for state_name, label in (("off", "switched off"), ("inactive", "not active"), ("running", "")):
            with self.subTest(state=state_name), patch(READERS, return_value=[InboxReader("Intake", state_name, 120)]):
                self.assertEqual(health.other_readers()[0]["state"], label)

        with patch(READERS, return_value=[]):
            response = self.card()

        self.assertNotContains(response, "This card controls bounce processing only")
