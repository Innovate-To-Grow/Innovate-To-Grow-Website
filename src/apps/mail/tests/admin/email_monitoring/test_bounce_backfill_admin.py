"""Email Monitoring → Bounce processing → "Read older mail again": Rescan since and the first-scan lookback through the
dashboard. Access (Mail app), POST with CSRF, validation in the site's time zone, the lease and pause rules, the
messages and the admin history. No scan is queued or run, and Microsoft Graph is never contacted."""

import re
from datetime import UTC, datetime, timedelta

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
from apps.core.services.email.bounces import state
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.email_monitoring.helpers import SENDER, monitoring_settings
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.admin.email_monitoring.controls import when
from apps.mail.services.email_monitoring import health

# The Rescan since button, disabled (the attribute sits between its class and its icon).
DISABLED_RESCAN = (
    'class="i2g-monitor-button" disabled><span class="material-symbols-outlined" aria-hidden="true">history'
    "</span>Rescan since"
)


def local_input(value) -> str:
    """A ``datetime-local`` value, as the browser posts it (the site's time zone, to the minute)."""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def to_minute(value):
    return value.replace(second=0, microsecond=0)


@override_settings(TIME_ZONE="America/Los_Angeles")
class BackfillTestCase(TestCase):
    """Signed in as a Mail-app staff member; Graph sends from and may read ``SENDER``, checkpoint ten minutes ago."""

    def setUp(self):
        cache.clear()
        create_graph_config(scope=(SENDER,), is_active=True, mailbox=SENDER)
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)
        self.staff = make_admin(apps=["mail"])
        self.client.force_login(self.staff)
        self.url = reverse("admin:mail_email_monitoring_bounce_processing")
        self.overview = reverse("admin:mail_email_monitoring")
        self.now = timezone.now()
        self.checkpoint = to_minute(self.now - timedelta(minutes=10))
        state.state_for(SENDER)
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=self.checkpoint)

    def row(self) -> EmailMonitorState:
        return EmailMonitorState.objects.get(mailbox=SENDER)

    def post(self, **data):
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(response.redirect_chain, [(self.overview, 302)])
        return response

    def messages(self, response) -> list[str]:
        return [str(message) for message in response.context["messages"]]

    def assertMessage(self, response, *parts):
        found = self.messages(response)
        self.assertTrue(any(all(part in text for part in parts) for text in found), found)

    def assertUnchanged(self):
        row = self.row()
        self.assertEqual((row.checkpoint_at, row.initial_lookback_hours), (self.checkpoint, None))
        self.assertFalse(LogEntry.objects.exists())

    def send_only_scope(self):
        """The Graph scope lets the site send as the mailbox but not read it: bounce processing is not active."""
        MicrosoftGraphMailboxScope.objects.update(permission=MicrosoftGraphMailboxScope.Permission.SEND)


class AccessTests(BackfillTestCase):
    def actions(self):
        return (
            {"action": "rescan", "since": local_input(self.now - timedelta(days=1))},
            {"action": "lookback", "lookback_hours": "100"},
        )

    def test_staff_without_the_mail_app_can_neither_rescan_nor_change_the_lookback(self):
        self.client.force_login(make_admin(apps=["cms", "core"], email="cms@example.com"))

        for data in self.actions():
            with self.subTest(action=data["action"]):
                self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.assertUnchanged()

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        self.client.logout()

        for data in self.actions():
            with self.subTest(action=data["action"]):
                response = self.client.post(self.url, data)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
        self.assertUnchanged()

    def test_superusers_may_rescan(self):
        self.client.force_login(make_superuser())

        self.post(action="rescan", since=local_input(self.now - timedelta(days=1)))

        self.assertEqual(self.row().checkpoint_at, to_minute(self.now - timedelta(days=1)))

    def test_a_get_never_changes_anything(self):
        response = self.client.get(self.url, {"action": "rescan", "since": local_input(self.now - timedelta(days=1))})

        self.assertEqual(response.status_code, 405)
        self.assertUnchanged()

    def test_a_post_without_the_csrf_token_is_refused_and_one_with_it_is_accepted(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        data = {"action": "rescan", "since": local_input(self.now - timedelta(days=1))}

        self.assertEqual(client.post(self.url, data).status_code, 403)
        self.assertUnchanged()
        page = client.get(self.overview).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        self.assertEqual(client.post(self.url, {**data, "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(self.row().checkpoint_at, to_minute(self.now - timedelta(days=1)))

    def test_every_control_on_the_card_posts_with_a_csrf_token(self):
        page = self.client.get(self.overview).content.decode()

        pattern = r'<form method="post" action="' + re.escape(self.url) + r'".*?</form>'
        forms = re.findall(pattern, page, re.S)
        actions = [re.search(r'name="action" value="(\w+)"', form).group(1) for form in forms]
        self.assertEqual(actions, ["scan", "pause", "rescan", "lookback"])
        for form in forms:
            self.assertIn('name="csrfmiddlewaretoken"', form)


class RescanTests(BackfillTestCase):
    def test_a_rescan_moves_the_checkpoint_back_and_says_what_happens_next(self):
        since = to_minute(self.now - timedelta(days=7))

        response = self.post(action="rescan", since=local_input(since))

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
            local_input(self.now + timedelta(hours=2)): "is in the future.",
            local_input(self.now - timedelta(days=91)): "is more than 90 days ago. Choose ",
        }
        with monitoring_settings(bounce_max_lookback_days=90):
            for value, reason in cases.items():
                with self.subTest(value=value):
                    response = self.post(action="rescan", since=value)

                    self.assertMessage(response, "The checkpoint was not moved: ", reason)
        self.assertUnchanged()

    def test_a_time_not_before_the_checkpoint_changes_nothing(self):
        response = self.post(action="rescan", since=local_input(self.now - timedelta(minutes=1)))

        self.assertMessage(
            response, f"Nothing changed: the checkpoint ({when(self.checkpoint)}) is already at or before"
        )
        self.assertUnchanged()

    def test_a_running_scan_is_never_overwritten(self):
        token = state.acquire_lease(SENDER, timezone.now())

        response = self.post(action="rescan", since=local_input(self.now - timedelta(days=1)))

        self.assertMessage(response, f"A scan of {SENDER} is running, so the checkpoint was not moved", "Try again")
        self.assertEqual((self.row().lease_token, self.row().checkpoint_at), (token, self.checkpoint))
        self.assertFalse(LogEntry.objects.exists())

    def test_while_paused_the_rescan_is_kept_for_later_and_processing_stays_paused(self):
        state.set_paused(SENDER, True)
        since = to_minute(self.now - timedelta(days=1))

        response = self.post(action="rescan", since=local_input(since))

        self.assertMessage(response, "once bounce processing is resumed (it is paused)")
        self.assertEqual((self.row().paused, self.row().checkpoint_at), (True, since))
        self.assertFalse(BackgroundJob.objects.exists())

    def test_before_the_first_scan_it_sets_where_the_first_scan_starts(self):
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=None)
        since = to_minute(self.now - timedelta(days=5))

        response = self.post(action="rescan", since=local_input(since))

        self.assertMessage(response, f"its first scan reads mail received since {when(since)}")
        self.assertEqual(self.row().checkpoint_at, since)

    def test_switched_off_bounce_processing_is_left_alone(self):
        with monitoring_settings(bounce_processing_enabled=False):
            response = self.post(action="rescan", since=local_input(self.now - timedelta(days=1)))

        self.assertMessage(response, "Bounce processing is turned off (EMAIL_BOUNCE_PROCESSING_ENABLED).")
        self.assertUnchanged()

    def test_a_mailbox_the_processor_may_not_read_is_refused_with_the_reason(self):
        since = local_input(self.now - timedelta(days=1))

        with monitoring_settings(bounce_mailboxes=("other@ucmerced.edu",)):
            outside = self.post(action="rescan", since=since)
        self.send_only_scope()
        send_only = self.post(action="rescan", since=since)

        self.assertMessage(outside, f"{SENDER} is not in the bounce-processing mailbox allow-list")
        self.assertMessage(send_only, f"does not grant read permission on {SENDER}")
        self.assertUnchanged()


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
        self.assertContains(response, "now 72 hours (the default)")
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

    def test_a_running_scan_shows_on_the_card(self):
        state.acquire_lease(SENDER, timezone.now())

        response = self.client.get(self.overview)

        self.assertTrue(response.context["health"]["bounces"]["scan_running"])
        self.assertContains(response, "running now (started")

    def test_the_rescan_button_is_disabled_when_the_mailbox_cannot_be_read(self):
        self.send_only_scope()

        response = self.client.get(self.overview)

        self.assertContains(response, DISABLED_RESCAN)
