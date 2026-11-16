from unittest.mock import patch

from django.core.management import CommandError

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    SMTPProviderConfig,
)
from apps.core.tests.project.commands.graph.test_verify_service_configs_graph import _VerifyServiceConfigsGraphCase


class VerifyServiceConfigsGraphTest(_VerifyServiceConfigsGraphCase):
    def test_missing_email_config_does_not_mention_graph(self):
        out = self._run()

        self.assertIn("FAIL: EmailServiceConfig selects SES", out)
        self.assertNotIn("Graph", out)

    def test_unselected_and_unconfigured_graph_is_not_mentioned_with_smtp(self):
        self._create_email(provider="smtp")
        self._create_smtp()

        out = self._run("--strict")

        self.assertIn("Service config verification passed.", out)
        self.assertNotIn("Graph", out)

    def test_inactive_graph_config_is_not_mentioned_when_another_provider_is_selected(self):
        self._create_email(provider="ses")
        self._create_aws()
        self._create_graph(is_active=False)

        self.assertNotIn("Graph", self._run("--strict"))

    def test_unselected_but_configured_graph_is_reported_ok(self):
        self._create_graph()
        for provider, create_provider in (("ses", self._create_aws), ("smtp", self._create_smtp)):
            EmailServiceConfig.objects.all().delete()
            self._create_email(provider=provider)
            create_provider()
            with self.subTest(provider):
                out = self._run("--strict")

                self.assertIn("MicrosoftGraphProviderConfig: OK", out)
                self.assertIn("Service config verification passed.", out)
                self.assertNotIn("FAIL", out)

    def test_unsupported_provider_is_still_reported_even_when_graph_is_configured(self):
        email = self._create_email(provider="ses")
        EmailServiceConfig.objects.filter(pk=email.pk).update(provider="unsupported")
        self._create_graph()

        out = self._run()
        with self.assertRaises(CommandError):
            self._run("--strict")

        self.assertIn("FAIL: EmailServiceConfig selects unsupported provider", out)
        self.assertNotIn("Service config verification passed.", out)

    def test_ses_selection_is_unchanged(self):
        self._create_email(provider="ses")
        self._create_aws()

        self.assertIn("Service config verification passed.", self._run("--strict"))

        AWSCredentialConfig.objects.all().delete()
        out = self._run()
        self.assertIn("FAIL: EmailServiceConfig selects SES", out)
        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_smtp_selection_is_unchanged(self):
        self._create_email(provider="smtp")
        self._create_smtp()

        self.assertIn("Service config verification passed.", self._run("--strict"))

        SMTPProviderConfig.objects.all().delete()
        out = self._run()
        self.assertIn("FAIL: EmailServiceConfig selects SMTP", out)
        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_policy_only_check_does_not_load_graph_credentials(self):
        self._create_email()
        self._create_graph()

        with patch(
            "apps.core.management.operations.provider_checks.MicrosoftGraphProviderConfig.load",
            side_effect=AssertionError("Policy-only verification must not load Graph credentials."),
        ):
            out = self._run("--send-verification-only")

        self.assertIn("SendVerificationConfig:", out)
        self.assertNotIn("Graph", out)
