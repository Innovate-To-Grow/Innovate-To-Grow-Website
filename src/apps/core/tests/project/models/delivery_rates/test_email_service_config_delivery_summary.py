from django.test import TestCase

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    SMTPProviderConfig,
)
from apps.core.tests.graph_helpers import private_key_lines
from apps.core.tests.project.models.graph.config.test_microsoft_graph_config import (
    CLIENT_ID,
    MAILBOX,
    TENANT_ID,
    make_graph,
)


class EmailServiceConfigDeliverySummaryTest(TestCase):
    def email(self, provider, **overrides):
        values = {"name": "Prod", "is_active": True, "provider": provider, "from_email": MAILBOX}
        return EmailServiceConfig.objects.create(**values | overrides)

    def test_graph_summary_names_the_sender_mailbox(self):
        make_graph(is_active=True, mailbox="shared@example.com")

        self.assertEqual(self.email("graph").delivery_summary, "Microsoft Graph (shared@example.com)")

    def test_graph_summary_falls_back_to_the_from_address_without_a_mailbox(self):
        make_graph(is_active=True, mailbox="")

        self.assertEqual(
            self.email("graph", from_email="noreply@example.com").delivery_summary,
            "Microsoft Graph (noreply@example.com)",
        )

    def test_ses_summary_names_the_region(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="not-a-real-key",
            secret_access_key="not-a-real-aws-secret",
            default_region="eu-west-1",
        )

        self.assertEqual(self.email("ses").delivery_summary, "AWS SES (eu-west-1)")

    def test_smtp_summary_names_the_host_and_port(self):
        SMTPProviderConfig.objects.create(name="SMTP", is_active=True, host="smtp.example.com", port=2525)

        self.assertEqual(self.email("smtp").delivery_summary, "SMTP (smtp.example.com:2525)")

    def test_unconfigured_delivery_says_so_for_every_provider(self):
        for provider in ("ses", "smtp", "graph"):
            with self.subTest(provider):
                self.assertEqual(self.email(provider).delivery_summary, "Not configured")
        self.assertEqual(EmailServiceConfig().delivery_summary, "Not configured")

    def test_summaries_never_include_credentials(self):
        make_graph(is_active=True)
        summary = self.email("graph").delivery_summary

        for line in private_key_lines():
            self.assertNotIn(line, summary)
        self.assertNotIn(CLIENT_ID, summary)
        self.assertNotIn(TENANT_ID, summary)

    def test_str_uses_the_provider_label(self):
        config = self.email("graph")
        self.assertEqual(str(config), "Prod: Microsoft Graph not configured (active)")

        make_graph(is_active=True)
        self.assertEqual(str(config), "Prod: Microsoft Graph (active)")
