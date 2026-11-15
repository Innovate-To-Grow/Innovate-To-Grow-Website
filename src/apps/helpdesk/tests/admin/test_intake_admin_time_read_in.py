from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.utils import timezone

from apps.core.models import (
    BackgroundJob,
)
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.helpdesk.tests.admin.test_intake_admin import IntakeAdminTestCase, posted, to_minute

from ...admin.intake.controls import when
from ...models import HelpdeskSettings, IntakeState
from ...services.intake import state as intake_state
from ..corpus import SITE


class RescanTests(IntakeAdminTestCase):
    def test_the_time_is_read_in_the_site_time_zone(self):
        wall = timezone.localtime(self.now - timedelta(days=3)).replace(hour=9, minute=30, second=0, microsecond=0)

        self.post(action="rescan", since=wall.strftime("%Y-%m-%dT%H:%M"))

        self.assertEqual(f"{timezone.localtime(self.row().checkpoint_at):%H:%M}", "09:30")

    def test_a_time_a_daylight_saving_change_makes_ambiguous_or_skips_is_refused(self):
        for value in ("2026-11-01T01:30", "2027-03-14T02:30"):
            with self.subTest(value=value):
                response = self.post(action="rescan", since=value)

                self.assertMessage(
                    response, "The intake checkpoint was not moved:", "it may be ambiguous or it may not exist"
                )
        self.assertUnchanged()

    def test_invalid_times_are_refused_with_the_reason(self):
        cases = {
            "": "enter the date and time to rescan from.",
            "last week": "enter a valid date and time.",
            posted(self.now + timedelta(hours=2)): "is in the future.",
            posted(self.now - timedelta(days=31)): "is more than 30 days ago. Choose ",
        }
        with monitoring_settings(inbox_max_lookback_days=30):
            for value, reason in cases.items():
                with self.subTest(value=value):
                    response = self.post(action="rescan", since=value)

                    self.assertMessage(response, "The intake checkpoint was not moved: ", reason)
        self.assertUnchanged()

    def test_a_time_not_before_the_checkpoint_changes_nothing(self):
        response = self.post(action="rescan", since=posted(self.now - timedelta(minutes=1)))

        self.assertMessage(
            response, f"Nothing changed: the intake checkpoint ({when(self.checkpoint)}) is already at or before"
        )
        self.assertUnchanged()

    def test_a_running_scan_is_never_overwritten(self):
        token = intake_state.acquire_lease(SITE, timezone.now())

        response = self.post(action="rescan", since=posted(self.now - timedelta(days=1)))

        self.assertMessage(
            response, f"An intake scan of {SITE} is running, so the checkpoint was not moved", "Try again"
        )
        self.assertEqual((self.row().lease_token, self.row().checkpoint_at), (token, self.checkpoint))
        self.assertFalse(LogEntry.objects.exists())

    def test_while_paused_or_switched_off_the_rescan_waits_and_nothing_else_changes(self):
        intake_state.set_paused(SITE, True)
        since = to_minute(self.now - timedelta(days=1))

        paused = self.post(action="rescan", since=posted(since))
        HelpdeskSettings.objects.update(enabled=False)
        off = self.post(action="rescan", since=posted(since - timedelta(days=1)))

        self.assertMessage(paused, "once the intake is resumed (it is paused)")
        self.assertMessage(off, "once the helpdesk is switched on")
        self.assertEqual((self.row().paused, self.row().checkpoint_at), (True, since - timedelta(days=1)))
        self.assertFalse(BackgroundJob.objects.exists())

    def test_before_the_first_scan_it_sets_where_the_first_scan_starts(self):
        IntakeState.objects.filter(mailbox=SITE).update(checkpoint_at=None)
        since = to_minute(self.now - timedelta(days=5))

        response = self.post(action="rescan", since=posted(since))

        self.assertMessage(response, f"its first scan reads mail received since {when(since)}")
        self.assertEqual(self.row().checkpoint_at, since)

    def test_a_mailbox_the_intake_may_not_read_is_refused_with_the_reason(self):
        since = posted(self.now - timedelta(days=1))
        with monitoring_settings(bounce_mailboxes=("other@ucmerced.edu",)):
            outside = self.post(action="rescan", since=since)
        self.send_only_scope()
        send_only = self.post(action="rescan", since=since)

        self.assertMessage(outside, f"{SITE} is not in the bounce-processing mailbox allow-list")
        self.assertMessage(send_only, f"does not grant read permission on {SITE}")
        self.assertUnchanged()
