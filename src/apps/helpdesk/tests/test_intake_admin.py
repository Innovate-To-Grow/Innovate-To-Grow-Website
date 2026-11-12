"""Helpdesk → Settings → the intake card: its controls (Scan now, Pause / Resume, Rescan since, first-scan lookback)
through the admin. Access (the Helpdesk grant), POST with CSRF, validation in the site's time zone, the lease and pause
rules, the messages and the admin history, and the decoupling both ways: the intake's controls never change bounce
processing, and the Email Monitoring card's never change the intake. Microsoft Graph is never contacted."""

import re
from datetime import UTC, timedelta

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    BackgroundJob,
    EmailMonitorState,
    EmailServiceConfig,
    MicrosoftGraphMailboxScope,
    MicrosoftGraphProviderConfig,
)
from apps.core.services.db_tools.safe_orm.constants import DENIED_MODEL_LABELS
from apps.core.services.email.bounces import state as bounce_state
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings

from ..admin.intake import when
from ..models import HelpdeskSettings, IntakeState
from ..services.ingest import jobs as ingest_jobs
from ..services.intake import jobs as intake_jobs
from ..services.intake import state as intake_state
from . import corpus
from .corpus import SITE
from .helpers import FakeReader, helpdesk_staff, make_admin, make_superuser, queue

ACTIONS = ("scan", "pause", "rescan", "lookback")
DISABLED_RESCAN = (
    'class="i2g-helpdesk-button" disabled><span class="material-symbols-outlined" aria-hidden="true">history'
    "</span>Rescan since"
)
DISABLED_SCAN = (
    'class="i2g-helpdesk-button" disabled><span class="material-symbols-outlined" aria-hidden="true">sync'
    "</span>Scan now"
)


def posted(value) -> str:
    """A minute posted with an explicit UTC offset (a wall time near a daylight-saving change could be ambiguous)."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:00Z")


def to_minute(value):
    return value.replace(second=0, microsecond=0)


@override_settings(TIME_ZONE="America/Los_Angeles")
class IntakeAdminTestCase(TestCase):
    """Signed in with the Helpdesk grant; Graph sends from and may read ``SITE``. The intake's checkpoint is ten
    minutes ago; bounce processing's (its own row) an hour ago."""

    def setUp(self):
        cache.clear()
        create_graph_config(scope=(SITE,), is_active=True, mailbox=SITE)
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SITE)
        self.settings_row = HelpdeskSettings.objects.create()
        self.staff = helpdesk_staff()
        self.client.force_login(self.staff)
        self.url = reverse("admin:helpdesk_intake")
        self.page = reverse("admin:helpdesk_helpdesksettings_change", args=[self.settings_row.pk])
        self.now = timezone.now()
        self.checkpoint = to_minute(self.now - timedelta(minutes=10))
        self.bounce_checkpoint = to_minute(self.now - timedelta(hours=1))
        intake_state.state_for(SITE)
        IntakeState.objects.filter(mailbox=SITE).update(checkpoint_at=self.checkpoint)
        bounce_state.state_for(SITE)
        EmailMonitorState.objects.filter(mailbox=SITE).update(checkpoint_at=self.bounce_checkpoint)

    def row(self) -> IntakeState:
        return IntakeState.objects.get(mailbox=SITE)

    def post(self, **data):
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(
            response.redirect_chain[0],
            (f"{reverse('admin:helpdesk_helpdesksettings_changelist')}#helpdesk-intake", 302),
        )
        self.assertEqual(response.request["PATH_INFO"], self.page)
        return response

    def messages(self, response) -> list[str]:
        return [str(message) for message in response.context["messages"]]

    def assertMessage(self, response, *parts):
        found = self.messages(response)
        self.assertTrue(any(all(part in text for part in parts) for text in found), found)

    def assertBounceUntouched(self):
        bounce = EmailMonitorState.objects.get(mailbox=SITE)
        self.assertEqual(
            (bounce.checkpoint_at, bounce.paused, bounce.initial_lookback_hours), (self.bounce_checkpoint, False, None)
        )

    def assertUnchanged(self):
        row = self.row()
        self.assertEqual((row.checkpoint_at, row.initial_lookback_hours, row.paused), (self.checkpoint, None, False))
        self.assertFalse(LogEntry.objects.exists())
        self.assertBounceUntouched()

    def send_only_scope(self):
        MicrosoftGraphMailboxScope.objects.update(permission=MicrosoftGraphMailboxScope.Permission.SEND)


class CardTests(IntakeAdminTestCase):
    def test_the_card_sits_above_the_settings_form_with_every_control_and_its_bounds(self):
        with monitoring_settings(inbox_max_lookback_days=90, inbox_initial_lookback_hours=72):
            response = self.client.get(self.page)

        page = response.content.decode()
        self.assertLess(page.index('id="helpdesk-intake"'), page.index('id="helpdesksettings_form"'))
        forms = re.findall(r'<form method="post" action="' + re.escape(self.url) + r'".*?</form>', page, re.S)
        self.assertEqual([re.search(r'name="action" value="(\w+)"', form).group(1) for form in forms], list(ACTIONS))
        for form in forms:
            self.assertIn('name="csrfmiddlewaretoken"', form)
        intake = response.context["helpdesk_intake"]
        self.assertEqual(
            (intake["mailbox"], intake["level"], intake["every"], intake["catch_up"]),
            (SITE, "waiting", "2 min", "30 s"),
        )
        self.assertContains(response, "Intake: reading the Inbox")
        self.assertContains(response, "<dt>Interval</dt><dd>every 2 min; every 30 s while catching up</dd>", html=False)
        self.assertContains(response, "its controls never change these")
        self.assertContains(response, "Rescan since (America/Los_Angeles)")
        self.assertContains(response, 'name="lookback_hours" min="1" max="2160" step="1"')
        self.assertContains(response, "now 72 hours (the default). Allowed: 1 to 2,160 hours;")
        self.assertContains(response, "The intake already has a checkpoint, so the lookback is not used")
        self.assertContains(response, "Pause intake")
        self.assertNotContains(response, DISABLED_RESCAN)
        self.assertNotContains(response, DISABLED_SCAN)

    def test_before_the_settings_are_saved_the_card_is_on_the_add_form(self):
        HelpdeskSettings.objects.all().delete()

        response = self.client.get(reverse("admin:helpdesk_helpdesksettings_changelist"), follow=True)

        self.assertEqual(response.request["PATH_INFO"], reverse("admin:helpdesk_helpdesksettings_add"))
        self.assertContains(response, 'id="helpdesk-intake"')

    def test_a_paused_intake_offers_resume_and_no_scan(self):
        intake_state.set_paused(SITE, True)

        response = self.client.get(self.page)

        self.assertContains(response, "Resume intake")
        self.assertContains(response, "<strong>Paused</strong>", html=False)
        self.assertContains(response, DISABLED_SCAN)

    def test_switched_off_the_card_says_so(self):
        HelpdeskSettings.objects.update(enabled=False)

        response = self.client.get(self.page)

        self.assertContains(response, "<strong>Switched off</strong>", html=False)
        self.assertContains(response, "nothing is read or imported")
        self.assertContains(response, DISABLED_SCAN)

    def test_a_mailbox_the_intake_cannot_read_shows_why(self):
        self.send_only_scope()

        response = self.client.get(self.page)

        self.assertContains(response, f"does not grant read permission on {SITE}")
        self.assertContains(response, DISABLED_RESCAN)

    def test_failures_and_the_last_scan_are_shown(self):
        IntakeState.objects.filter(mailbox=SITE).update(
            last_run_finished_at=self.now,
            last_error_at=self.now,
            last_error="Microsoft Graph returned HTTP 503.",
            consecutive_failures=2,
            last_run_stats={"listed": 7, "recorded": 3},
        )
        queue(corpus.message(), reader=FakeReader())

        response = self.client.get(self.page)

        self.assertContains(response, "2 scans in a row failed")
        self.assertContains(response, "Microsoft Graph returned HTTP 503.")
        self.assertContains(response, "Last scan: 7 messages listed, 3 new recorded for import")
        self.assertContains(response, "<dt>Waiting to be imported</dt><dd>1 message</dd>", html=False)


class AccessTests(IntakeAdminTestCase):
    def actions(self):
        return (
            {"action": "scan"},
            {"action": "pause"},
            {"action": "rescan", "since": posted(self.now - timedelta(days=1))},
            {"action": "lookback", "lookback_hours": "100"},
        )

    def test_staff_without_the_helpdesk_grant_can_change_nothing(self):
        self.client.force_login(make_admin(apps=["mail", "core"], email="mailer@example.com"))

        for data in self.actions():
            with self.subTest(action=data["action"]):
                self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.assertUnchanged()
        self.assertFalse(BackgroundJob.objects.exists())

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        self.client.logout()

        for data in self.actions():
            with self.subTest(action=data["action"]):
                response = self.client.post(self.url, data)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
        self.assertUnchanged()

    def test_superusers_may_use_the_controls(self):
        self.client.force_login(make_superuser(email="master@example.com"))

        self.post(action="pause")

        self.assertTrue(self.row().paused)

    def test_a_get_never_changes_anything(self):
        response = self.client.get(self.url, {"action": "pause"})

        self.assertEqual(response.status_code, 405)
        self.assertUnchanged()

    def test_a_post_without_the_csrf_token_is_refused_and_one_with_it_is_accepted(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        data = {"action": "rescan", "since": posted(self.now - timedelta(days=1))}

        self.assertEqual(client.post(self.url, data).status_code, 403)
        self.assertUnchanged()
        page = client.get(self.page).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        self.assertEqual(client.post(self.url, {**data, "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(self.row().checkpoint_at, to_minute(self.now - timedelta(days=1)))

    def test_an_unknown_action_is_refused(self):
        response = self.post(action="delete")

        self.assertMessage(response, "Unknown intake action.")
        self.assertUnchanged()


class ScanNowTests(IntakeAdminTestCase):
    def test_scan_now_queues_one_intake_scan(self):
        response = self.post(action="scan")

        self.assertMessage(response, f"An intake scan of {SITE} was queued")
        job = BackgroundJob.objects.get()
        self.assertEqual((job.kind, job.payload), (intake_jobs.INTAKE_JOB_KIND, {"requested": "manual"}))

    def test_nothing_is_queued_while_paused_switched_off_or_unreadable(self):
        intake_state.set_paused(SITE, True)
        paused = self.post(action="scan")
        intake_state.set_paused(SITE, False)
        HelpdeskSettings.objects.update(enabled=False)
        off = self.post(action="scan")
        HelpdeskSettings.objects.update(enabled=True)
        self.send_only_scope()
        unreadable = self.post(action="scan")

        self.assertMessage(paused, "is paused: resume it to scan")
        self.assertMessage(off, "The helpdesk is switched off")
        self.assertMessage(unreadable, f"does not grant read permission on {SITE}")
        self.assertFalse(BackgroundJob.objects.exists())


class PauseTests(IntakeAdminTestCase):
    def test_pause_holds_the_intake_only_and_is_recorded(self):
        response = self.post(action="pause")

        self.assertTrue(self.row().paused)
        self.assertMessage(
            response, f"Intake of {SITE} paused", "Bounce processing (Email Monitoring) is not affected."
        )
        entry = LogEntry.objects.get()
        self.assertEqual(
            (entry.user_id, entry.object_id, entry.change_message),
            (self.staff.pk, str(self.row().pk), "Intake paused."),
        )
        self.assertBounceUntouched()
        self.assertMessage(self.post(action="pause"), f"The intake of {SITE} is already paused; nothing changed.")
        self.assertEqual(LogEntry.objects.count(), 1)

    def test_resume_wakes_the_import_of_mail_that_waited(self):
        intake_state.set_paused(SITE, True)
        queue(corpus.message(), reader=FakeReader())

        response = self.post(action="resume")

        self.assertFalse(self.row().paused)
        self.assertMessage(response, f"Intake of {SITE} resumed: the next scan (within 2 min) continues")
        self.assertTrue(BackgroundJob.objects.filter(kind=ingest_jobs.INGEST_JOB_KIND).exists())
        self.assertMessage(self.post(action="resume"), f"The intake of {SITE} is already running")
        self.assertBounceUntouched()

    def test_like_the_lookback_it_works_while_the_mailbox_cannot_be_read(self):
        self.send_only_scope()

        self.post(action="pause")

        self.assertTrue(self.row().paused)

    def test_without_graph_there_is_no_mailbox_to_pause(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)

        response = self.post(action="pause")

        self.assertMessage(response, "Microsoft Graph is not configured")
        self.assertUnchanged()


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
