from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailCategory, EmailServiceConfig, OutboundEmail
from apps.core.tests.services.email_monitoring.helpers import make_attempt, make_bounce, make_email
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign
from apps.mail.tests.admin.email_monitoring.dashboard.test_unified_page_admin import FIGURE_LABEL, OVERVIEW_FIGURES


class OverviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        self.url = reverse("admin:mail_email_monitoring")

    def test_every_section_is_on_the_overview(self):
        failed = make_email(status=OutboundEmail.Status.FAILED, last_error="Microsoft Graph rejected the request.")
        make_attempt(failed, outcome="permanent", http_status=400, error_kind="bad_request")
        campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")
        make_email(campaign_id=campaign.pk)
        make_bounce(recipient="lost@example.com", match_method="unmatched")

        response = self.client.get(self.url)

        for heading in (
            'id="monitor-bounce-processing"',
            'id="monitor-key-figures"',
            'id="monitor-levels"',
            'id="monitor-recipients"',
            'id="monitor-attempts"',
            "Most recent sending error",
            'id="monitor-trends"',
            'data-chart="volume"',
            'data-chart="api"',
            'data-chart="bounces"',
            'id="monitor-breakdowns"',
            "Failed attempts by HTTP status",
            "Emails by category",
            "Top failure reasons",
            "Top bounce reasons",
            'id="monitor-campaigns"',
            reverse("admin:mail_email_monitoring_campaign", args=[campaign.pk]),
        ):
            self.assertContains(response, heading)

    def test_one_kpi_strip_and_every_figure_exactly_once(self):
        make_attempt(make_email(), http_status=202)

        response = self.client.get(self.url)
        html = response.content.decode()

        self.assertEqual(html.count('class="i2g-monitor-tiles"'), 1)
        strip = html.split("data-monitor-kpis>", 1)[1].split("</div>\n  <p", 1)[0]
        self.assertEqual(strip.count('class="i2g-monitor-tile"'), 6)
        labels = FIGURE_LABEL.findall(html)
        for label in OVERVIEW_FIGURES:
            self.assertEqual(labels.count(label), 1, label)
        # Amazon SES's own figures are on their tab only, not repeated here.
        for label in ("SES attempts", "Delivered by SES", "SES errors"):
            self.assertNotIn(label, labels)
        self.assertNotContains(response, ">Delivered<")

    def test_the_send_rate_is_shown_once_with_a_link_to_delivery_rates(self):
        with patch(
            "apps.mail.services.email_monitoring.dashboard.overview.email_send_rate_line", return_value="Now: 5/sec"
        ):
            response = self.client.get(self.url)

        self.assertContains(response, "Send rate: Now: 5/sec", count=1)
        self.assertContains(response, f'<a href="{reverse("admin:mail_delivery_rates")}">Delivery Rates</a>', count=1)

    def test_a_send_rate_that_cannot_be_read_never_breaks_the_page(self):
        with (
            patch(
                "apps.mail.services.email_monitoring.dashboard.overview.email_send_rate_line",
                side_effect=RuntimeError("x"),
            ),
            self.assertLogs("apps.mail.services.email_monitoring.dashboard.overview", "WARNING"),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["send_rate"], "")
        self.assertNotContains(response, "data-monitor-send-rate")

    def test_the_overview_never_reads_aws(self):
        # SES is the sender and AWS credentials are set, so an AWS read (CloudWatch, the suppression list, a Secrets
        # Manager key) would get as far as building a boto3 client. Check that no client is built at all. Building one
        # raises, so a read fails at once (a stand-in client would page CloudWatch forever), but the raise alone proves
        # nothing: the SES dashboard turns every AWS failure into a notice and the page would still load.
        no_client = AssertionError("the Overview must not build an AWS client")
        AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="AKIAEXAMPLE0000",
            secret_access_key="not-a-real-secret",
            default_region="us-west-2",
        )
        EmailServiceConfig.objects.create(
            name="Primary Sender", is_active=True, provider="ses", from_email="sender@example.com", max_send_rate=0
        )

        with (
            patch("boto3.client", side_effect=no_client) as client,
            patch("boto3.session.Session.client", side_effect=no_client) as session_client,
        ):
            page = self.client.get(self.url)
            data = self.client.get(reverse("admin:mail_email_monitoring_data"))

        self.assertEqual((page.status_code, data.status_code), (200, 200))
        client.assert_not_called()
        session_client.assert_not_called()
        self.assertContains(page, f'href="{reverse("admin:mail_email_monitoring_ses")}"')

    def test_the_response_time_names_microsoft_graph_whose_answers_it_averages(self):
        # Only the Graph provider records an HTTP answer (AttemptNotes.answered), and the average reads only attempts
        # with one, so the caption names Microsoft whatever the Provider filter says.
        make_attempt(make_email(), http_status=202, response_ms=300)
        make_attempt(make_email(provider="ses"), provider="ses", http_status=None, response_ms=900)

        response = self.client.get(self.url)

        self.assertEqual(response.context["figures"]["attempts"]["avg_response_ms"], 300)
        self.assertContains(response, "requests Microsoft answered", count=1)

    def test_the_probe_note_and_the_figures_still_leave_probes_out(self):
        make_email(category=EmailCategory.ACCESS_CHECK)

        response = self.client.get(self.url)

        self.assertEqual(response.context["figures"]["messages"]["total"], 0)
        self.assertContains(response, "1 Graph access check probe send in this range is listed in the email log")
