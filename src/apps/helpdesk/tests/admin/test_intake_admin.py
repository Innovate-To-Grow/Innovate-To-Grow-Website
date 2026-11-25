"""Helpdesk → Settings → the intake card: its controls (Scan now, Pause / Resume, Rescan since, first-scan lookback)
through the admin. Access (every Admin), POST with CSRF, validation in the site's time zone, the lease and pause
rules, the messages and the admin history, and the decoupling both ways: the intake's controls never change bounce
processing, and the Email Monitoring card's never change the intake. Microsoft Graph is never contacted."""

import re
from datetime import UTC, timedelta

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    EmailMonitorState,
    EmailServiceConfig,
    MicrosoftGraphMailboxScope,
)
from apps.core.services.email.bounces.scanning import state as bounce_state
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings

from ...models import HelpdeskSettings, IntakeState
from ...services.intake import state as intake_state
from .. import corpus
from ..corpus import SITE
from ..helpers import FakeReader, helpdesk_staff, queue

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
    """Signed in as an Admin; Graph sends from and may read ``SITE``. The intake's checkpoint is ten
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
