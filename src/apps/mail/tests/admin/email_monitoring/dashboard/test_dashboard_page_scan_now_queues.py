from django.urls import reverse

from apps.core.models import (
    BackgroundJob,
    EmailMonitorState,
    EmailServiceConfig,
    MicrosoftGraphMailboxScope,
)
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND
from apps.core.services.email.bounces.state import set_paused
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.email_monitoring.helpers import (
    monitoring_settings,
)
from apps.mail.tests.admin.email_monitoring.dashboard.test_dashboard_page import _PageCase


class PageTests(_PageCase):
    def test_scan_now_queues_a_scan_and_pause_and_resume_change_the_state(self):
        create_graph_config(scope=("i2g@ucmerced.edu",), is_active=True, mailbox="i2g@ucmerced.edu")
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email="i2g@ucmerced.edu")
        url = reverse("admin:mail_email_monitoring_bounce_processing")

        self.assertRedirects(
            self.client.post(url, {"action": "scan"}),
            reverse("admin:mail_email_monitoring"),
            fetch_redirect_response=False,
        )
        self.assertTrue(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).exists())
        self.client.post(url, {"action": "pause"})
        self.assertTrue(EmailMonitorState.objects.get(mailbox="i2g@ucmerced.edu").paused)
        self.client.post(url, {"action": "resume"})
        self.assertFalse(EmailMonitorState.objects.get(mailbox="i2g@ucmerced.edu").paused)

    def test_scan_now_queues_nothing_while_paused_switched_off_or_unreadable(self):
        # The card greys Scan now out in these cases; a stale page or a second tab gets the reason and no job, as the
        # helpdesk intake card does. A paused mailbox's scan would read nothing.
        mailbox = "i2g@ucmerced.edu"
        create_graph_config(scope=(mailbox,), is_active=True, mailbox=mailbox)
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=mailbox)
        url = reverse("admin:mail_email_monitoring_bounce_processing")

        def scan() -> list[str]:
            response = self.client.post(url, {"action": "scan"}, follow=True)
            return [str(message) for message in response.context["messages"]]

        set_paused(mailbox, True)
        paused = scan()
        set_paused(mailbox, False)
        with monitoring_settings(bounce_processing_enabled=False):
            off = scan()
        MicrosoftGraphMailboxScope.objects.update(permission=MicrosoftGraphMailboxScope.Permission.SEND)
        unreadable = scan()

        self.assertEqual(paused, [f"Bounce processing for {mailbox} is paused: resume it to scan."])
        self.assertEqual(off, ["Bounce processing is turned off (EMAIL_BOUNCE_PROCESSING_ENABLED)."])
        self.assertEqual(
            unreadable, [f"The Microsoft Graph mailbox scope does not grant read permission on {mailbox}."]
        )
        self.assertFalse(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).exists())

        MicrosoftGraphMailboxScope.objects.update(permission=MicrosoftGraphMailboxScope.Permission.SEND_AND_READ)
        self.assertEqual(scan(), ["A bounce scan was queued; the background worker runs it within a minute."])
        self.assertEqual(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).count(), 1)

    def test_an_unknown_action_is_refused_with_the_reason(self):
        response = self.client.post(
            reverse("admin:mail_email_monitoring_bounce_processing"), {"action": "drop"}, follow=True
        )

        self.assertContains(response, "Microsoft Graph is not configured")
