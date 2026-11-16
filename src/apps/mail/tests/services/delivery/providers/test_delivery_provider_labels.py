"""Admin labels name the real email provider instead of assuming AWS SES (no AWS calls, fake secrets only)."""

import re
from contextlib import contextmanager
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphProviderConfig, SMTPProviderConfig
from apps.core.services.aws.credentials import AwsCredentialsError
from apps.core.tests.graph_helpers import create_graph_config
from apps.event.tests.helpers import make_superuser

# Graph senders used in this module; the mailbox scope rules have their own tests.
GRAPH_TEST_SCOPE = ("mailer@example.com", "campaigns@ucmerced.edu", "admin@example.com")

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "66666666-7777-8888-9999-000000000000"
PROVIDERS = (("ses", "AWS SES"), ("smtp", "SMTP"), ("graph", "Microsoft Graph"))


@contextmanager
def no_aws_calls():
    """The dashboard reads CloudWatch and SES; make both report 'credentials not configured' without a network."""
    unconfigured = AwsCredentialsError("AWS credentials are not configured.")
    with (
        patch("apps.mail.services.campaign.dashboard._cloudwatch_client", side_effect=unconfigured),
        patch("apps.mail.services.campaign.dashboard._sesv2_client", side_effect=unconfigured),
    ):
        yield


class ProviderFixtureMixin:
    """An active sender plus a configuration for every provider; tests only switch ``EmailServiceConfig.provider``."""

    def create_provider_configs(self, *, graph_mailbox="mailer@example.com"):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="AKIATEST1234",
            secret_access_key="not-a-real-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
        )
        SMTPProviderConfig.objects.create(name="Backup SMTP", is_active=True, host="smtp.example.com", port=587)
        create_graph_config(
            scope=GRAPH_TEST_SCOPE,
            name="Outlook Sender",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            mailbox=graph_mailbox,
        )
        self.sender = EmailServiceConfig.objects.create(
            name="Primary Sender",
            is_active=True,
            provider="ses",
            from_email="campaigns@ucmerced.edu",
            from_name="Innovate to Grow",
            max_send_rate=0,
        )

    def use_provider(self, provider):
        self.sender.provider = provider
        self.sender.save()


class CampaignChangelistLabelTests(ProviderFixtureMixin, TestCase):
    def setUp(self):
        self.create_provider_configs()
        self.changelist_url = reverse("admin:mail_emailcampaign_changelist")

    def sender_panel(self):
        html = self.client.get(self.changelist_url).content.decode()
        match = re.search(r"Email Sender\s*</h4>(.*?)<h4", html, re.S)
        self.assertIsNotNone(match, "the Email Sender panel is missing")
        return match.group(1)

    def provider_row(self, panel):
        match = re.search(r"Provider:</span>\s*<span[^>]*>\s*(.*?)\s*</span>", panel, re.S)
        self.assertIsNotNone(match, "the Provider row is missing")
        return match.group(1)

    def test_heading_says_email_sender_not_ses_email_sender(self):
        response = self.client.get(self.changelist_url)

        self.assertContains(response, "Email Sender")
        self.assertNotContains(response, "SES Email Sender")

    def test_provider_row_shows_the_delivery_summary_of_every_provider(self):
        expected = {
            "ses": "AWS SES (us-west-2)",
            "smtp": "SMTP (smtp.example.com:587)",
            "graph": "Microsoft Graph (mailer@example.com)",
        }
        for provider, summary in expected.items():
            with self.subTest(provider=provider):
                self.use_provider(provider)

                self.assertEqual(self.provider_row(self.sender_panel()), summary)

    def test_graph_without_a_mailbox_shows_the_from_email(self):
        MicrosoftGraphProviderConfig.objects.update(mailbox="")
        self.use_provider("graph")

        self.assertEqual(self.provider_row(self.sender_panel()), "Microsoft Graph (campaigns@ucmerced.edu)")

    def test_aws_key_row_appears_only_for_ses(self):
        for provider in ("ses", "smtp", "graph"):
            with self.subTest(provider=provider):
                self.use_provider(provider)

                panel = self.sender_panel()

                if provider == "ses":
                    self.assertIn("AWS Key:", panel)
                    self.assertIn("...1234", panel)
                else:
                    self.assertNotIn("AWS Key:", panel)
                    self.assertNotIn("1234", panel)
                    self.assertNotIn("AWS SES", panel)

    def test_provider_without_active_configuration_reads_not_configured(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)
        self.use_provider("graph")

        panel = self.sender_panel()

        self.assertEqual(self.provider_row(panel), "Not configured")
        self.assertNotIn("Microsoft Graph (", panel)
        self.assertNotIn("AWS Key:", panel)

    def test_ses_without_aws_credentials_reads_not_configured(self):
        AWSCredentialConfig.objects.all().delete()

        panel = self.sender_panel()

        self.assertEqual(self.provider_row(panel), "Not configured")
        self.assertNotIn("AWS Key:", panel)
