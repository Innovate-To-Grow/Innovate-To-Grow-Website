"""Email Monitoring → Bounce processing → "Read older mail again": Rescan since and the first-scan lookback through the
dashboard. Access (Mail app), POST with CSRF, validation in the site's time zone, the lease and pause rules, the
messages and the admin history. No scan is queued or run, and Microsoft Graph is never contacted."""

import re
from datetime import UTC, timedelta

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    EmailMonitorState,
    EmailServiceConfig,
    MicrosoftGraphMailboxScope,
)
from apps.core.services.email.bounces.scanning import state
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.email_monitoring.helpers import SENDER
from apps.event.tests.helpers import make_admin, make_superuser

# The Rescan since button, disabled (the attribute sits between its class and its icon).
DISABLED_RESCAN = (
    'class="i2g-monitor-button" disabled><span class="material-symbols-outlined" aria-hidden="true">history'
    "</span>Rescan since"
)


def local_input(value) -> str:
    """A ``datetime-local`` value, as the browser posts it (the site's time zone, to the minute)."""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def posted(value) -> str:
    """The same minute, posted with an explicit UTC offset. ``datetime-local`` posts a wall time, which the form reads in
    the site's time zone (tested on its own with fixed times); a wall time computed from "now" could fall in the hour a
    daylight-saving change makes ambiguous, and the form rightly refuses it, so the other tests post an instant."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:00Z")


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
            {"action": "rescan", "since": posted(self.now - timedelta(days=1))},
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

        self.post(action="rescan", since=posted(self.now - timedelta(days=1)))

        self.assertEqual(self.row().checkpoint_at, to_minute(self.now - timedelta(days=1)))

    def test_a_get_never_changes_anything(self):
        response = self.client.get(self.url, {"action": "rescan", "since": posted(self.now - timedelta(days=1))})

        self.assertEqual(response.status_code, 405)
        self.assertUnchanged()

    def test_a_post_without_the_csrf_token_is_refused_and_one_with_it_is_accepted(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        data = {"action": "rescan", "since": posted(self.now - timedelta(days=1))}

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
        # The delivery status card below it posts to the same view (Check permissions; Sync now while trace is on).
        self.assertEqual(actions, ["scan", "pause", "rescan", "lookback", "permissions"])
        for form in forms:
            self.assertIn('name="csrfmiddlewaretoken"', form)


READERS = "apps.mail.services.email_monitoring.dashboard.health.inbox_readers"
INTAKE_URL = "/admin/helpdesk/helpdesksettings/#helpdesk-intake"
