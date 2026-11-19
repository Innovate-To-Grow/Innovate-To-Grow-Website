from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    EmailCategory,
    OutboundEmail,
)
from apps.core.tests.services.email_monitoring.helpers import (
    make_attempt,
    make_bounce,
    make_email,
)
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog


class _PageCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())


class PageTests(_PageCase):
    def test_the_overview_separates_levels_and_never_says_delivered_without_trace_data(self):
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
        self.assertEqual(response.context["figures"]["messages"]["delivered"], 0)
        log = self.client.get(reverse("admin:mail_email_monitoring_emails"))
        self.assertNotContains(log, "i2g-monitor-chip--delivered")

    def test_an_email_shows_delivered_only_with_its_trace_data(self):
        email = make_email(delivery_status="delivered", trace_status="delivered", trace_checked_at=timezone.now())

        log = self.client.get(reverse("admin:mail_email_monitoring_emails"))
        page = self.client.get(reverse("admin:mail_email_monitoring_email", args=[email.pk]))

        self.assertContains(log, "i2g-monitor-chip--delivered")
        self.assertContains(page, "<code>delivered</code> · checked")
        self.assertContains(page, "handed the email to the recipient")

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
