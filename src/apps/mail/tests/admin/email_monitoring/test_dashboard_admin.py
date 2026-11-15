"""Mail → Delivery Operations → Email Monitoring: who may open it, what each page shows, and its controls."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    BackgroundJob,
    EmailCategory,
    EmailMonitorState,
    EmailServiceConfig,
    MicrosoftGraphMailboxScope,
    OutboundEmail,
)
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND
from apps.core.services.email.bounces.state import set_paused
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.email_monitoring.helpers import (
    make_attempt,
    make_bounce,
    make_email,
    monitoring_settings,
)
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import EmailCampaign, RecipientLog

PAGES = (
    ("admin:mail_email_monitoring", ()),
    ("admin:mail_email_monitoring_data", ()),
    ("admin:mail_email_monitoring_emails", ()),
    ("admin:mail_email_monitoring_bounces", ()),
)


class AccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.email = make_email()
        self.campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")

    def urls(self):
        return [reverse(name, args=args) for name, args in PAGES] + [
            reverse("admin:mail_email_monitoring_email", args=[self.email.pk]),
            reverse("admin:mail_email_monitoring_campaign", args=[self.campaign.pk]),
        ]

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_staff_without_the_mail_app_are_refused_everywhere(self):
        self.client.force_login(make_admin(apps=["cms"]))

        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(reverse("admin:mail_email_monitoring_bounce_processing"), {"action": "scan"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).exists())

    def test_mail_staff_and_superusers_may_open_every_page(self):
        for user in (make_admin(apps=["mail"]), make_superuser()):
            self.client.force_login(user)
            for url in self.urls():
                with self.subTest(user=user.pk, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_bounce_processing_controls_only_take_post(self):
        self.client.force_login(make_superuser())

        self.assertEqual(self.client.get(reverse("admin:mail_email_monitoring_bounce_processing")).status_code, 405)


class PageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_overview_separates_levels_and_never_says_delivered(self):
        failed = make_email(status=OutboundEmail.Status.FAILED, last_error="Microsoft Graph rejected the request.")
        make_attempt(
            failed, outcome="permanent", http_status=400, error_kind="bad_request", error_code="ErrorInvalidRecipients"
        )
        make_attempt(make_email(), http_status=202)

        response = self.client.get(reverse("admin:mail_email_monitoring"))

        self.assertContains(response, "Total outgoing emails")
        self.assertContains(response, "Total intended recipients")
        self.assertContains(response, "429 throttling incidents")
        self.assertContains(response, "Most recent sending error")
        self.assertContains(response, "ErrorInvalidRecipients")
        self.assertContains(response, 'id="i2g-monitor-charts"')
        self.assertContains(response, "Monitoring began")
        self.assertNotContains(response, ">Delivered<")
        self.assertEqual(response.context["figures"]["messages"]["failed"], 1)

    def test_the_data_endpoint_returns_figures_and_charts(self):
        make_email()

        data = self.client.get(reverse("admin:mail_email_monitoring_data"), {"range": "24h"}).json()

        self.assertEqual(data["range"]["key"], "24h")
        self.assertEqual(data["figures"]["messages"]["total"], 1)
        self.assertIn(len(data["charts"]["volume"]["labels"]), (24, 25))  # hourly buckets

    def test_an_invalid_custom_range_falls_back_and_says_why(self):
        response = self.client.get(reverse("admin:mail_email_monitoring"), {"range": "custom", "start": "2026-11-09"})

        self.assertContains(response, "Enter a start and an end date")
        self.assertEqual(response.context["scope"].key, "7d")

    def test_impossible_custom_dates_never_fail_the_page(self):
        for start, end in (("2026-02-30", "2026-03-01"), ("9999-12-30", "9999-12-31")):
            for name in ("admin:mail_email_monitoring", "admin:mail_email_monitoring_data"):
                with self.subTest(start=start, page=name):
                    response = self.client.get(reverse(name), {"range": "custom", "start": start, "end": end})
                    self.assertEqual(response.status_code, 200)

    def test_the_email_log_filters_sorts_and_links_to_each_email(self):
        make_email(recipient="alpha@example.com", category=EmailCategory.SIGN_IN)
        target = make_email(recipient="beta@example.com", category=EmailCategory.CAMPAIGN, status="failed")
        make_email(recipient="probe@example.com", category=EmailCategory.ACCESS_CHECK)

        response = self.client.get(
            reverse("admin:mail_email_monitoring_emails"), {"status": "failed", "sort": "recipient", "dir": "asc"}
        )

        self.assertEqual([row.pk for row in response.context["page"].object_list], [target.pk])
        self.assertContains(response, reverse("admin:mail_email_monitoring_email", args=[target.pk]))
        all_rows = self.client.get(reverse("admin:mail_email_monitoring_emails")).context["page"].object_list
        self.assertNotIn("probe@example.com", [row.recipient for row in all_rows])

    def test_an_email_page_shows_every_attempt_its_ids_and_its_bounces(self):
        email = make_email(status="accepted", delivery_status="failure_confirmed", bounce_classification="hard")
        make_attempt(
            email,
            1,
            outcome="transient",
            http_status=429,
            error_kind="throttled",
            retry_after_seconds=17,
            request_id="req-429",
            client_request_id="cli-1",
        )
        make_attempt(email, 2, request_id="req-202")
        make_bounce(email=email, reason="Recipient not found", status_code="5.1.10", match_method="message_id")

        response = self.client.get(reverse("admin:mail_email_monitoring_email", args=[email.pk]))

        for text in (
            "req-429",
            "cli-1",
            "req-202",
            "Throttled (HTTP 429)",
            "17 s",
            "Recipient not found",
            "5.1.10",
            "Delivery failure confirmed",
            "Hard bounce",
        ):
            self.assertContains(response, text)
        self.assertContains(response, "does not prove the email reached")

    def test_the_bounce_list_shows_unmatched_reports(self):
        make_bounce(
            recipient="lost@example.com",
            match_method="unmatched",
            match_note="No email the site sent matches the report.",
        )

        response = self.client.get(reverse("admin:mail_email_monitoring_bounces"), {"match": "unmatched"})

        self.assertContains(response, "lost@example.com")
        self.assertContains(response, "No email the site sent matches the report.")

    def test_a_campaign_page_lists_failed_recipients_and_its_recipient_log(self):
        campaign = EmailCampaign.objects.create(
            subject="News", body="<p>x</p>", status="sent", total_recipients=2, sent_at=timezone.now()
        )
        make_email(campaign_id=campaign.pk, recipient="ok@example.com")
        failed = make_email(
            campaign_id=campaign.pk,
            recipient="bad@example.com",
            status="failed",
            last_error="Microsoft Graph rejected the request.",
        )
        make_attempt(failed, outcome="permanent", http_status=400, error_kind="bad_request")

        response = self.client.get(reverse("admin:mail_email_monitoring_campaign", args=[campaign.pk]))

        self.assertContains(response, "bad@example.com")
        self.assertContains(response, "Intended recipients")
        self.assertEqual(response.context["monitoring"]["failed_total"], 1)
        self.assertNotContains(response, "sent before email monitoring began")

    def test_a_campaign_sent_before_monitoring_began_says_so(self):
        make_email()
        campaign = EmailCampaign.objects.create(
            subject="Old", body="<p>x</p>", status="sent", sent_at=timezone.now() - timedelta(days=30)
        )
        RecipientLog.objects.create(campaign=campaign, email_address="old@example.com", status="sent")

        response = self.client.get(reverse("admin:mail_email_monitoring_campaign", args=[campaign.pk]))

        self.assertContains(response, "sent before email monitoring began")
        self.assertEqual(response.context["monitoring"]["recipient_log"], {"sent": 1})

    def test_a_campaign_monitoring_began_during_says_how_much_is_covered(self):
        campaign = EmailCampaign.objects.create(subject="Mid", body="<p>x</p>", status="sent", sent_at=timezone.now())
        for address in ("a@example.com", "b@example.com"):
            RecipientLog.objects.create(campaign=campaign, email_address=address, status="sent")
        RecipientLog.objects.create(campaign=campaign, email_address="c@example.com", status="pending")
        make_email(campaign_id=campaign.pk, recipient="b@example.com")

        response = self.client.get(reverse("admin:mail_email_monitoring_campaign", args=[campaign.pk]))

        self.assertContains(response, "Telemetry covers 1 of the 2 recipients")

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


class CampaignActionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_a_sent_campaign_links_to_its_monitoring(self):
        campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")

        response = self.client.get(reverse("admin:mail_emailcampaign_delivery_monitoring_action", args=[campaign.pk]))

        self.assertRedirects(
            response, reverse("admin:mail_email_monitoring_campaign", args=[campaign.pk]), fetch_redirect_response=False
        )
