from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GoogleCredentialConfig,
    SMTPProviderConfig,
)

VALID_GOOGLE_JSON = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key": "test-only-not-a-real-key",  # noqa: S105 — test fixture, satisfies presence check only
    "client_email": "svc@test-project.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}


class VerifyServiceConfigsCommandTest(TestCase):
    def setUp(self):
        EmailServiceConfig.objects.all().delete()
        GoogleCredentialConfig.objects.all().delete()
        AWSCredentialConfig.objects.all().delete()
        SMTPProviderConfig.objects.all().delete()
        # Default: no origination number auto-detected from AWS (no live calls in tests).
        patcher = patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
        self.mock_origination_available = patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, *args):
        out = StringIO()
        err = StringIO()
        call_command("verify_service_configs", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def _create_email(self, *, from_email: str = "i2g@g.ucmerced.edu", provider: str = "ses"):
        return EmailServiceConfig.objects.create(
            name="Production",
            is_active=True,
            provider=provider,
            from_email=from_email,
        )

    def _create_smtp(self):
        return SMTPProviderConfig.objects.create(
            name="SMTP",
            is_active=True,
            host="smtp.example.com",
            port=587,
            username="mailer",
            password="secret",
            use_tls=True,
        )

    def _create_aws(self, *, sms_from_number: str = ""):
        return AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-west-2",
            sms_from_number=sms_from_number,
        )

    def test_fails_strict_when_email_missing(self):
        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_passes_when_email_and_aws_configured(self):
        self._create_email()
        self._create_aws()
        out, _ = self._run("--strict")
        self.assertIn("Service config verification passed.", out)

    def test_fails_strict_when_email_from_address_missing(self):
        self._create_email(from_email="")
        self._create_aws()

        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_fails_strict_when_email_from_address_has_invalid_syntax(self):
        self._create_email(from_email="not-an-email")
        self._create_aws()

        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_smtp_provider_does_not_require_aws(self):
        self._create_email(provider="smtp")
        self._create_smtp()

        out, _ = self._run("--strict")

        self.assertIn("Service config verification passed.", out)

    def test_unsupported_provider_fails_even_when_smtp_is_configured(self):
        email = self._create_email(provider="ses")
        EmailServiceConfig.objects.filter(pk=email.pk).update(provider="unsupported")
        self._create_smtp()

        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_smtp_provider_requires_valid_smtp_config(self):
        self._create_email(provider="smtp")

        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_require_aws_is_independent_of_smtp_email_selection(self):
        self._create_email(provider="smtp")
        self._create_smtp()

        with self.assertRaises(CommandError):
            self._run("--strict", "--require-aws")

    def test_require_sms_is_independent_of_smtp_email_selection(self):
        self._create_email(provider="smtp")
        self._create_smtp()

        with self.assertRaises(CommandError):
            self._run("--strict", "--require-sms")

    def test_warns_when_optional_configs_missing(self):
        self._create_email()
        self._create_aws()
        out, _ = self._run()
        self.assertIn("AWS SNS SMS", out)
        self.assertIn("GoogleCredentialConfig", out)
        self.assertIn("WARN", out)

    def test_strict_with_require_sms_fails_when_sms_missing(self):
        self._create_email()
        self._create_aws()
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-sms")

    def test_strict_with_require_sms_passes_when_configured(self):
        self._create_email()
        self._create_aws(sms_from_number="+12065550000")
        out, _ = self._run("--strict", "--require-sms")
        self.assertIn("passed", out)

    def test_strict_with_require_sms_passes_when_number_auto_resolved(self):
        self._create_email()
        self._create_aws()  # no manual override; number comes from AWS
        self.mock_origination_available.return_value = True
        out, _ = self._run("--strict", "--require-sms")
        self.assertIn("passed", out)

    def test_strict_with_require_google_fails_without_google(self):
        self._create_email()
        self._create_aws()
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-google")

    def test_strict_with_require_google_passes_when_configured(self):
        self._create_email()
        self._create_aws()
        GoogleCredentialConfig.objects.create(
            name="Sheets",
            is_active=True,
            credentials_json=VALID_GOOGLE_JSON,
        )
        out, _ = self._run("--strict", "--require-google")
        self.assertIn("passed", out)

    def test_email_without_aws_fails_strict(self):
        self._create_email()
        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_require_aws_fails_when_no_aws_config(self):
        self._create_email()
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-aws")

    def test_non_strict_with_failures_reports_and_returns(self):
        """Non-strict mode with a required failure prints FAIL but does not raise."""
        # EmailServiceConfig is required; with no AWS config email_ok is False ->
        # a failure is recorded, but without --strict the command returns cleanly.
        self._create_email()
        out, _ = self._run()
        self.assertIn("FAIL: EmailServiceConfig selects SES", out)
        # The success line is NOT printed because we returned early at the failures branch.
        self.assertNotIn("Service config verification passed.", out)
