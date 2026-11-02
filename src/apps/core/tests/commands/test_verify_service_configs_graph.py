"""verify_service_configs with the Microsoft Graph email provider."""

from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GoogleCredentialConfig,
    MicrosoftGraphProviderConfig,
    SMTPProviderConfig,
)
from apps.core.tests.graph_helpers import create_graph_config, install_test_certificate, private_key_lines

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class VerifyServiceConfigsGraphTest(TestCase):
    def setUp(self):
        EmailServiceConfig.objects.all().delete()
        GoogleCredentialConfig.objects.all().delete()
        AWSCredentialConfig.objects.all().delete()
        SMTPProviderConfig.objects.all().delete()
        MicrosoftGraphProviderConfig.objects.all().delete()
        # No origination number is auto-detected from AWS (no live calls in tests).
        patcher = patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, *args):
        out = StringIO()
        call_command("verify_service_configs", *args, stdout=out, stderr=StringIO(), no_color=True)
        return out.getvalue()

    def _create_email(self, *, provider: str = "graph", from_email: str = "i2g@g.ucmerced.edu"):
        return EmailServiceConfig.objects.create(
            name="Production", is_active=True, provider=provider, from_email=from_email
        )

    def _create_graph(self, **overrides):
        values = {
            "name": "Graph",
            "is_active": True,
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "mailbox": "i2g@g.ucmerced.edu",
        }
        return create_graph_config(scope=("i2g@g.ucmerced.edu",), **values | overrides)

    def _create_unvalidated_graph(self, certificate=True, **overrides):
        """An active row that save() would refuse, as a script or an older release could leave behind."""
        row = MicrosoftGraphProviderConfig(name="Broken", is_active=True, tenant_id=TENANT_ID, client_id=CLIENT_ID)
        for field, value in overrides.items():
            setattr(row, field, value)
        MicrosoftGraphProviderConfig.objects.bulk_create([row])
        if certificate:
            install_test_certificate(row)
        return row

    def _create_smtp(self):
        return SMTPProviderConfig.objects.create(
            name="SMTP", is_active=True, host="smtp.example.com", port=587, username="mailer", password="not-a-real-pw"
        )

    def _create_aws(self):
        return AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="not-a-real-key",
            secret_access_key="not-a-real-aws-secret",
            default_region="us-west-2",
        )

    # --- Microsoft Graph selected -------------------------------------------------------------------

    def test_selected_and_configured_graph_passes_strict(self):
        self._create_email()
        self._create_graph()

        out = self._run("--strict")

        self.assertIn("MicrosoftGraphProviderConfig: OK", out)
        self.assertIn("EmailServiceConfig: OK", out)
        self.assertIn("Service config verification passed.", out)
        self.assertNotIn("FAIL", out)

    def test_graph_provider_does_not_require_aws(self):
        self._create_email()
        self._create_graph()

        out = self._run("--strict")

        self.assertIn("AWSCredentialConfig: missing", out)
        self.assertIn("Service config verification passed.", out)

    def test_require_aws_is_independent_of_graph_selection(self):
        self._create_email()
        self._create_graph()

        with self.assertRaises(CommandError):
            self._run("--strict", "--require-aws")

    def test_require_sms_is_independent_of_graph_selection(self):
        self._create_email()
        self._create_graph()

        with self.assertRaises(CommandError):
            self._run("--strict", "--require-sms")

    def test_selected_graph_without_a_usable_config_fails_strict(self):
        scenarios = {
            "no row": lambda: None,
            "inactive row": lambda: self._create_graph(is_active=False),
            "active row without a certificate": lambda: self._create_unvalidated_graph(certificate=False),
            "active row without a tenant": lambda: self._create_unvalidated_graph(tenant_id=""),
            "active row without a client id": lambda: self._create_unvalidated_graph(client_id=""),
        }
        for label, create in scenarios.items():
            MicrosoftGraphProviderConfig.objects.all().delete()
            EmailServiceConfig.objects.all().delete()
            self._create_email()
            create()
            with self.subTest(label), self.assertRaises(CommandError):
                self._run("--strict")

    def test_selected_graph_without_a_config_reports_the_failure_without_strict(self):
        self._create_email()

        out = self._run()

        failures = [line for line in out.splitlines() if line.startswith("FAIL:")]
        self.assertIn("MicrosoftGraphProviderConfig: MISSING", out)
        self.assertIn("EmailServiceConfig: MISSING", out)
        self.assertEqual(len(failures), 1)
        self.assertIn("Microsoft Graph", failures[0])
        self.assertIn("MicrosoftGraphProviderConfig", failures[0])
        self.assertNotIn("Service config verification passed.", out)

    def test_selected_graph_with_a_missing_sender_address_fails_on_the_address(self):
        self._create_email(from_email="")
        self._create_graph()

        out = self._run()

        self.assertIn("FAIL: EmailServiceConfig From address is empty or invalid.", out)
        self.assertNotIn("Microsoft Graph, but", out)

    def test_output_never_contains_key_material(self):
        self._create_email()
        self._create_graph()
        configured = self._run("--strict")

        MicrosoftGraphProviderConfig.objects.all().delete()
        self._create_unvalidated_graph(tenant_id="")
        broken = self._run()

        for line in private_key_lines():
            self.assertNotIn(line, configured + broken)
        self.assertIn("FAIL", broken)

    # --- Microsoft Graph not selected ---------------------------------------------------------------

    def test_unselected_and_unconfigured_graph_is_not_mentioned_with_ses(self):
        self._create_email(provider="ses")
        self._create_aws()

        out = self._run("--strict")

        self.assertIn("Service config verification passed.", out)
        self.assertIn("WARN:", out)  # the optional SMS and Google checks still warn, but never about Graph
        self.assertNotIn("Graph", out)

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

    # --- unsupported provider and unchanged providers -----------------------------------------------

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
            "apps.core.management.commands.verify_service_configs.MicrosoftGraphProviderConfig.load",
            side_effect=AssertionError("Policy-only verification must not load Graph credentials."),
        ):
            out = self._run("--send-verification-only")

        self.assertIn("SendVerificationConfig:", out)
        self.assertNotIn("Graph", out)
