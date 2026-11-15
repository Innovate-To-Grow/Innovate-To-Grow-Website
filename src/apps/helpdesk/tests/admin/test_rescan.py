from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.test import override_settings
from django.urls import reverse

from apps.core.models import (
    BackgroundJob,
    EmailMonitorState,
)
from apps.core.services.db_tools.safe_orm.constants import DENIED_MODEL_LABELS
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.helpdesk.tests.admin.test_intake_admin import IntakeAdminTestCase, posted, to_minute

from ...admin.intake.controls import when
from ...models import HelpdeskSettings, IntakeState
from ...services.intake import jobs as intake_jobs
from ...services.intake import state as intake_state
from ..corpus import SITE
from ..helpers import make_admin


class RescanTests(IntakeAdminTestCase):
    def test_a_rescan_moves_the_intake_checkpoint_back_and_nothing_else(self):
        since = to_minute(self.now - timedelta(days=7))

        response = self.post(action="rescan", since=posted(since))

        self.assertEqual(self.row().checkpoint_at, since)
        self.assertMessage(
            response,
            f"Rescan set for {SITE}: the intake checkpoint moved back from {when(self.checkpoint)} to {when(since)}.",
            "at the next scheduled scan (within 2 min), or sooner with Scan now",
            "messages it already recorded are skipped, so no ticket is made twice",
            "Bounce processing (Email Monitoring) is not affected.",
        )
        entry = LogEntry.objects.get()
        self.assertEqual((entry.user_id, entry.object_id), (self.staff.pk, str(self.row().pk)))
        self.assertIn("Rescan since", entry.change_message)
        self.assertFalse(BackgroundJob.objects.exists())  # no scan was queued
        self.assertBounceUntouched()


class LookbackTests(IntakeAdminTestCase):
    def test_staff_set_the_lookback_and_the_change_is_recorded(self):
        with monitoring_settings(inbox_initial_lookback_hours=72):
            response = self.post(action="lookback", lookback_hours="240")

        self.assertEqual(self.row().initial_lookback_hours, 240)
        self.assertMessage(
            response,
            f"Intake first-scan lookback for {SITE} set to 240 hours.",
            "It applies only while the intake has no checkpoint, and it has one",
        )
        entry = LogEntry.objects.get()
        self.assertEqual(
            (entry.user_id, entry.change_message), (self.staff.pk, "First-scan lookback: default (72 h) → 240 h.")
        )
        self.assertBounceUntouched()

    def test_an_empty_value_restores_the_default_and_an_unchanged_one_says_so(self):
        intake_state.set_lookback(SITE, 240)

        with monitoring_settings(inbox_initial_lookback_hours=72):
            reset = self.post(action="lookback", lookback_hours="")
            again = self.post(action="lookback", lookback_hours="")

        self.assertIsNone(self.row().initial_lookback_hours)
        self.assertMessage(reset, f"Intake first-scan lookback for {SITE} set to the default (72 hours).")
        self.assertMessage(again, f"The intake's first-scan lookback for {SITE} is already the default (72 hours)")

    def test_before_the_first_scan_it_says_the_first_scan_reads_that_far_back(self):
        IntakeState.objects.filter(mailbox=SITE).update(checkpoint_at=None)

        response = self.post(action="lookback", lookback_hours="1")

        self.assertMessage(response, "set to 1 hour. The first scan reads that far back.")

    def test_values_outside_the_bounds_or_not_whole_hours_are_refused(self):
        with monitoring_settings(inbox_max_lookback_days=90, inbox_initial_lookback_hours=72):
            for value, reason in (
                ("0", "enter 1 to 2,160 hours, or leave it empty for the default (72 hours)."),
                ("2161", "enter 1 to 2,160 hours"),
                ("ten", "enter a whole number of hours."),
                ("1.5", "enter a whole number of hours."),
            ):
                with self.subTest(value=value):
                    response = self.post(action="lookback", lookback_hours=value)

                    self.assertMessage(response, "The first-scan lookback was not saved: ", reason)
        self.assertUnchanged()

    def test_like_pause_it_can_be_set_while_the_mailbox_cannot_be_read(self):
        self.send_only_scope()

        self.post(action="lookback", lookback_hours="48")

        self.assertEqual(self.row().initial_lookback_hours, 48)


class DecouplingTests(IntakeAdminTestCase):
    """The Email Monitoring card's controls change bounce processing only, and say who else reads the Inbox."""

    def setUp(self):
        super().setUp()
        self.client.force_login(make_admin(apps=["mail"], email="mailer@example.com"))
        self.bounce_url = reverse("admin:mail_email_monitoring_bounce_processing")

    def test_the_bounce_cards_controls_never_change_the_intake(self):
        self.client.post(self.bounce_url, {"action": "pause"})
        self.client.post(self.bounce_url, {"action": "rescan", "since": posted(self.now - timedelta(days=2))})
        self.client.post(self.bounce_url, {"action": "lookback", "lookback_hours": "48"})

        bounce = EmailMonitorState.objects.get(mailbox=SITE)
        self.assertEqual((bounce.paused, bounce.initial_lookback_hours), (True, 48))
        self.assertEqual(bounce.checkpoint_at, to_minute(self.now - timedelta(days=2)))
        row = self.row()
        self.assertEqual((row.paused, row.checkpoint_at, row.initial_lookback_hours), (False, self.checkpoint, None))

    def test_the_email_monitoring_card_lists_the_intake_with_its_own_cadence_and_state(self):
        overview = reverse("admin:mail_email_monitoring")
        link = f'<a href="{reverse("admin:helpdesk_helpdesksettings_changelist")}#helpdesk-intake">Helpdesk intake</a>'

        running = self.client.get(overview)
        intake_state.set_paused(SITE, True)
        paused = self.client.get(overview)

        self.assertContains(running, "This card controls bounce processing only")
        self.assertContains(running, f"{link}, every 2 min.")
        self.assertContains(
            running, "<dt>Interval</dt><dd>every 10 min; every 2 min while catching up</dd>", html=False
        )
        self.assertContains(paused, f"{link}, every 2 min (paused).")


class SettingsAndPrivacyTests(IntakeAdminTestCase):
    def test_every_helpdesk_model_is_out_of_reach_of_the_ai_assistant_and_the_cli(self):
        from django.apps import apps

        labels = {model._meta.label_lower for model in apps.get_app_config("helpdesk").get_models()}

        self.assertIn("helpdesk.intakestate", labels)
        self.assertEqual(labels - DENIED_MODEL_LABELS, set())

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_saving_the_settings_restarts_the_intake_and_the_import(self):
        HelpdeskSettings.objects.update(enabled=False)
        form = self.client.get(self.page).context["adminform"].form
        data = {name: form[name].value() for name in form.fields}
        data.update(enabled="on", pause_while_campaign_sending="on")

        response = self.client.post(self.page, data)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(BackgroundJob.objects.filter(kind=intake_jobs.INTAKE_JOB_KIND).exists())

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_saving_the_settings_switched_off_queues_nothing(self):
        form = self.client.get(self.page).context["adminform"].form
        data = {name: form[name].value() for name in form.fields}
        data.update(enabled="", pause_while_campaign_sending="on")

        response = self.client.post(self.page, data)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(HelpdeskSettings.load().enabled)
        self.assertFalse(BackgroundJob.objects.exists())
