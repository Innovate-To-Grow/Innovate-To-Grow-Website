import json
import re

from django.test import TestCase
from django.urls import reverse

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.event.tests.helpers import make_event
from apps.mail.services.campaign.dashboard import get_delivery_dashboard_data
from apps.mail.tests.services.delivery.providers.test_delivery_provider_labels import (
    PROVIDERS,
    ProviderFixtureMixin,
    no_aws_calls,
)


class EventFormLabelTests(ProviderFixtureMixin, TestCase):
    def setUp(self):
        self.create_provider_configs()
        self.event = make_event()
        self.change_url = reverse("admin:event_event_change", args=[self.event.pk])

    def email_panel(self):
        html = self.client.get(self.change_url).content.decode()
        start = html.index("Email Service</span>")
        return html[start : html.index("SMS Service</span>", start)]

    def provider_row(self, panel):
        match = re.search(r"Provider:</span>\s*<span[^>]*>\s*(.*?)\s*</span>", panel, re.S)
        self.assertIsNotNone(match, "the Provider row is missing")
        return match.group(1)

    def test_provider_row_shows_the_delivery_summary_of_every_provider(self):
        expected = {
            "ses": "AWS SES (us-west-2)",
            "smtp": "SMTP (smtp.example.com:587)",
            "graph": "Microsoft Graph (mailer@example.com)",
        }
        for provider, summary in expected.items():
            with self.subTest(provider=provider):
                self.use_provider(provider)

                panel = self.email_panel()

                self.assertEqual(self.provider_row(panel), summary)
                self.assertIn("campaigns@ucmerced.edu", panel)

    def test_graph_without_a_mailbox_shows_the_from_email(self):
        MicrosoftGraphProviderConfig.objects.update(mailbox="")
        self.use_provider("graph")

        self.assertEqual(self.provider_row(self.email_panel()), "Microsoft Graph (campaigns@ucmerced.edu)")

    def test_unconfigured_provider_reads_not_configured_and_never_claims_ses(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)
        self.use_provider("graph")

        panel = self.email_panel()

        self.assertEqual(self.provider_row(panel), "Not configured")
        self.assertNotIn("AWS SES", panel)

    def test_add_form_shows_the_same_provider_summary(self):
        self.use_provider("graph")

        response = self.client.get(reverse("admin:event_event_add"))

        self.assertContains(response, "Microsoft Graph (mailer@example.com)")
        self.assertNotContains(response, "AWS SES (")


class DashboardProviderMetaTests(ProviderFixtureMixin, TestCase):
    def setUp(self):
        self.create_provider_configs()

    def test_payload_names_the_active_provider_and_its_label(self):
        for provider, label in PROVIDERS:
            with self.subTest(provider=provider):
                self.use_provider(provider)

                with no_aws_calls():
                    payload = get_delivery_dashboard_data(days=7)

                self.assertEqual(payload["aws"]["provider"], provider)
                self.assertEqual(payload["aws"]["provider_label"], label)
                json.dumps(payload)

    def test_payload_keeps_the_existing_ses_metadata_for_any_provider(self):
        self.use_provider("graph")

        with no_aws_calls():
            aws = get_delivery_dashboard_data(days=7)["aws"]

        self.assertEqual(aws["email_config"], "Primary Sender")
        self.assertEqual(aws["aws_config"], "Primary AWS")
        self.assertEqual(aws["region"], "us-west-2")
        self.assertEqual(aws["iam_key"], "...1234")
        self.assertEqual(aws["source_address"], "Innovate to Grow <campaigns@ucmerced.edu>")
        self.assertFalse(aws["metrics_available"])

    def test_payload_defaults_to_ses_when_no_sender_is_active(self):
        EmailServiceConfig.objects.all().delete()

        with no_aws_calls():
            aws = get_delivery_dashboard_data(days=7)["aws"]

        self.assertEqual((aws["provider"], aws["provider_label"]), ("ses", "AWS SES"))


class SesTabNoticeTests(ProviderFixtureMixin, TestCase):
    """Email Monitoring → Amazon SES (the former Delivery Dashboard) names the active provider before anything else."""

    def setUp(self):
        self.create_provider_configs()
        self.page_url = reverse("admin:mail_email_monitoring_ses")

    def test_a_graph_sender_gets_the_provider_notice_not_the_ses_one(self):
        self.use_provider("graph")

        with no_aws_calls():
            response = self.client.get(self.page_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.context["aws"]["provider"], response.context["aws"]["provider_label"]),
            ("graph", "Microsoft Graph"),
        )
        self.assertEqual(response.context["notice"]["key"], "provider")
        self.assertContains(response, "The active email provider is Microsoft Graph")
        self.assertContains(response, "which reports no delivery events here")
        # A Graph or SMTP sender is never "SES configured", so the provider notice has to win, or staff would be
        # told that AWS SES is not fully configured.
        self.assertNotContains(response, "AWS SES is not fully configured")

    def test_an_ses_sender_without_aws_access_is_told_so(self):
        with no_aws_calls():
            response = self.client.get(self.page_url)

        self.assertEqual(response.context["aws"]["provider"], "ses")
        self.assertNotEqual(response.context["notice"]["key"], "provider")
        self.assertNotContains(response, "The active email provider is")

    def test_data_endpoints_name_the_provider(self):
        self.use_provider("graph")

        for name in ("admin:mail_email_monitoring_ses_data", "admin:mail_delivery_dashboard_data"):
            with self.subTest(name=name), no_aws_calls():
                response = self.client.get(reverse(name))

            self.assertEqual(response.status_code, 200)
            aws = response.json()["aws"]
            self.assertEqual((aws["provider"], aws["provider_label"]), ("graph", "Microsoft Graph"))
