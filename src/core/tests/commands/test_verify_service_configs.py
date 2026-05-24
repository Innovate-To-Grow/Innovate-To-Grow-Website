from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GoogleCredentialConfig,
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

    def _run(self, *args):
        out = StringIO()
        err = StringIO()
        call_command("verify_service_configs", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def _create_email(self):
        return EmailServiceConfig.objects.create(
            name="Production",
            is_active=True,
            smtp_host="smtp.example.com",
            smtp_username="user",
            smtp_password="pw",
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

    def test_smtp_only_email_is_sufficient_without_aws(self):
        self._create_email()
        out, _ = self._run("--strict")
        self.assertIn("passed", out)

    def test_require_aws_fails_when_no_aws_config(self):
        self._create_email()
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-aws")
