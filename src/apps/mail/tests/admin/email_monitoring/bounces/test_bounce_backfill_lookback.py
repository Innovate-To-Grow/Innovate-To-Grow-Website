from django.contrib.admin.models import LogEntry

from apps.core.models import (
    BackgroundJob,
    EmailMonitorState,
    MicrosoftGraphProviderConfig,
)
from apps.core.services.email.bounces.scanning import state
from apps.core.tests.services.email_monitoring.helpers import SENDER, monitoring_settings
from apps.mail.tests.admin.email_monitoring.bounces.test_bounce_backfill_admin import BackfillTestCase


class LookbackTests(BackfillTestCase):
    def test_staff_set_the_lookback_and_the_change_is_recorded(self):
        with monitoring_settings(bounce_initial_lookback_hours=72):
            response = self.post(action="lookback", lookback_hours="240")

        self.assertEqual(self.row().initial_lookback_hours, 240)
        self.assertMessage(
            response,
            f"First-scan lookback for {SENDER} set to 240 hours.",
            "It applies only while the mailbox has no checkpoint, and it has one",
            "use Rescan since to read older mail now.",
        )
        entry = LogEntry.objects.get()
        self.assertEqual(
            (entry.user_id, entry.change_message), (self.staff.pk, "First-scan lookback: default (72 h) → 240 h.")
        )
        self.assertEqual(self.row().checkpoint_at, self.checkpoint)
        self.assertFalse(BackgroundJob.objects.exists())

    def test_an_empty_value_restores_the_default(self):
        state.set_lookback(SENDER, 240)

        with monitoring_settings(bounce_initial_lookback_hours=72):
            response = self.post(action="lookback", lookback_hours="")

        self.assertIsNone(self.row().initial_lookback_hours)
        self.assertMessage(response, f"First-scan lookback for {SENDER} set to the default (72 hours).")

    def test_before_the_first_scan_it_says_the_first_scan_reads_that_far_back(self):
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=None)

        response = self.post(action="lookback", lookback_hours="1000")

        self.assertMessage(response, "set to 1,000 hours. The first scan reads that far back.")

    def test_values_outside_the_bounds_or_not_whole_hours_are_refused(self):
        with monitoring_settings(bounce_max_lookback_days=90, bounce_initial_lookback_hours=72):
            for value, reason in (
                ("0", "enter 1 to 2,160 hours, or leave it empty for the default (72 hours)."),
                ("2161", "enter 1 to 2,160 hours"),
                ("-5", "enter 1 to 2,160 hours"),
                ("ten", "enter a whole number of hours."),
                ("1.5", "enter a whole number of hours."),
            ):
                with self.subTest(value=value):
                    response = self.post(action="lookback", lookback_hours=value)

                    self.assertMessage(response, "The first-scan lookback was not saved: ", reason)
        self.assertUnchanged()

    def test_an_unchanged_value_says_so_and_records_nothing(self):
        with monitoring_settings(bounce_initial_lookback_hours=72):
            response = self.post(action="lookback", lookback_hours="")

        self.assertMessage(response, f"The first-scan lookback for {SENDER} is already the default (72 hours)")
        self.assertUnchanged()

    def test_the_shortest_lookback_reads_as_one_hour(self):
        response = self.post(action="lookback", lookback_hours="1")

        self.assertEqual(self.row().initial_lookback_hours, 1)
        self.assertMessage(response, f"First-scan lookback for {SENDER} set to 1 hour.")

    def test_like_pause_it_can_be_set_while_the_mailbox_cannot_be_read(self):
        self.send_only_scope()

        self.post(action="lookback", lookback_hours="48")

        self.assertEqual(self.row().initial_lookback_hours, 48)

    def test_without_graph_there_is_no_mailbox_to_set_it_for(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)

        for data in ({"action": "lookback", "lookback_hours": "48"}, {"action": "rescan", "since": "2026-11-10T09:00"}):
            with self.subTest(action=data["action"]):
                response = self.post(**data)

                self.assertMessage(response, "Microsoft Graph is not configured")
        self.assertUnchanged()
