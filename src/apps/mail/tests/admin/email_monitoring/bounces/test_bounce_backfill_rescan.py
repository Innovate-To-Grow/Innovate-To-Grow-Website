from datetime import UTC, timedelta

from django.contrib.admin.models import LogEntry
from django.utils import timezone

from apps.core.models import (
    BackgroundJob,
    EmailMonitorState,
)
from apps.core.services.email.bounces.scanning import state
from apps.core.tests.services.email_monitoring.helpers import SENDER, monitoring_settings
from apps.mail.admin.email_monitoring.controls import when
from apps.mail.tests.admin.email_monitoring.bounces.test_bounce_backfill_admin import (
    BackfillTestCase,
    posted,
    to_minute,
)


class RescanTests(BackfillTestCase):
    def test_a_rescan_moves_the_checkpoint_back_and_says_what_happens_next(self):
        since = to_minute(self.now - timedelta(days=7))

        response = self.post(action="rescan", since=posted(since))

        self.assertEqual(self.row().checkpoint_at, since)
        self.assertMessage(
            response,
            f"Rescan set for {SENDER}: the checkpoint moved back from {when(self.checkpoint)} to {when(since)}.",
            "at the next scheduled scan, or sooner with Scan now",
            "reports already recorded are skipped, so none is counted twice",
        )
        entry = LogEntry.objects.get()
        self.assertEqual((entry.user_id, entry.object_id), (self.staff.pk, str(self.row().pk)))
        self.assertIn("Rescan since", entry.change_message)
        self.assertFalse(BackgroundJob.objects.exists())  # no scan was queued

    def test_the_time_is_read_in_the_site_time_zone(self):
        wall = timezone.localtime(self.now - timedelta(days=3)).replace(hour=9, minute=30, second=0, microsecond=0)

        self.post(action="rescan", since=wall.strftime("%Y-%m-%dT%H:%M"))

        saved = self.row().checkpoint_at
        self.assertEqual(saved, wall)
        self.assertEqual(f"{timezone.localtime(saved):%H:%M}", "09:30")

    def test_a_time_with_an_explicit_offset_is_taken_as_given(self):
        since = to_minute(self.now - timedelta(days=2))

        self.post(action="rescan", since=since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))

        self.assertEqual(self.row().checkpoint_at, since)

    def test_a_time_a_daylight_saving_change_makes_ambiguous_or_skips_is_refused(self):
        # 1:30 on Nov 1, 2026 happens twice in Los Angeles; 2:30 on Mar 14, 2027 never happens.
        for value in ("2026-11-01T01:30", "2027-03-14T02:30"):
            with self.subTest(value=value):
                response = self.post(action="rescan", since=value)

                self.assertMessage(response, "The checkpoint was not moved:", "it may be ambiguous or it may not exist")
        self.assertUnchanged()

    def test_invalid_times_are_refused_with_the_reason(self):
        cases = {
            "": "enter the date and time to rescan from.",
            "last week": "enter a valid date and time.",
            posted(self.now + timedelta(hours=2)): "is in the future.",
            posted(self.now - timedelta(days=91)): "is more than 90 days ago. Choose ",
        }
        with monitoring_settings(bounce_max_lookback_days=90):
            for value, reason in cases.items():
                with self.subTest(value=value):
                    response = self.post(action="rescan", since=value)

                    self.assertMessage(response, "The checkpoint was not moved: ", reason)
        self.assertUnchanged()

    def test_a_time_not_before_the_checkpoint_changes_nothing(self):
        response = self.post(action="rescan", since=posted(self.now - timedelta(minutes=1)))

        self.assertMessage(
            response, f"Nothing changed: the checkpoint ({when(self.checkpoint)}) is already at or before"
        )
        self.assertUnchanged()

    def test_a_running_scan_is_never_overwritten(self):
        token = state.acquire_lease(SENDER, timezone.now())

        response = self.post(action="rescan", since=posted(self.now - timedelta(days=1)))

        self.assertMessage(response, f"A scan of {SENDER} is running, so the checkpoint was not moved", "Try again")
        self.assertEqual((self.row().lease_token, self.row().checkpoint_at), (token, self.checkpoint))
        self.assertFalse(LogEntry.objects.exists())

    def test_while_paused_the_rescan_is_kept_for_later_and_processing_stays_paused(self):
        state.set_paused(SENDER, True)
        since = to_minute(self.now - timedelta(days=1))

        response = self.post(action="rescan", since=posted(since))

        self.assertMessage(response, "once bounce processing is resumed (it is paused)")
        self.assertEqual((self.row().paused, self.row().checkpoint_at), (True, since))
        self.assertFalse(BackgroundJob.objects.exists())

    def test_before_the_first_scan_it_sets_where_the_first_scan_starts(self):
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=None)
        since = to_minute(self.now - timedelta(days=5))

        response = self.post(action="rescan", since=posted(since))

        self.assertMessage(response, f"its first scan reads mail received since {when(since)}")
        self.assertEqual(self.row().checkpoint_at, since)

    def test_switched_off_bounce_processing_is_left_alone(self):
        with monitoring_settings(bounce_processing_enabled=False):
            response = self.post(action="rescan", since=posted(self.now - timedelta(days=1)))

        self.assertMessage(response, "Bounce processing is turned off (EMAIL_BOUNCE_PROCESSING_ENABLED).")
        self.assertUnchanged()

    def test_a_mailbox_the_processor_may_not_read_is_refused_with_the_reason(self):
        since = posted(self.now - timedelta(days=1))

        with monitoring_settings(bounce_mailboxes=("other@ucmerced.edu",)):
            outside = self.post(action="rescan", since=since)
        self.send_only_scope()
        send_only = self.post(action="rescan", since=since)

        self.assertMessage(outside, f"{SENDER} is not in the bounce-processing mailbox allow-list")
        self.assertMessage(send_only, f"does not grant read permission on {SENDER}")
        self.assertUnchanged()
