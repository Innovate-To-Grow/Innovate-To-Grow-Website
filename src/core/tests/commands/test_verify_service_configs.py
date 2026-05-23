from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GoogleCredentialConfig,
    SMSServiceConfig,
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
        SMSServiceConfig.objects.all().delete()
        GoogleCredentialConfig.objects.all().delete()
        AWSCredentialConfig.objects.all().delete()

    def _run(self, *args):
        out = StringIO()
        err = StringIO()
        call_command("verify_service_configs", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def _create_email(self, *, ses: bool = True):
        return EmailServiceConfig.objects.create(
            name="Production",
            is_active=True,
            ses_access_key_id="key" if ses else "",
            ses_secret_access_key="secret" if ses else "",
            ses_region="us-west-2",
            smtp_host="smtp.example.com",
            smtp_username="user",
            smtp_password="pw",
        )

    def test_fails_strict_when_email_missing(self):
        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_passes_when_only_email_configured(self):
        self._create_email(ses=True)
        out, _ = self._run("--strict")
        self.assertIn("Service config verification passed.", out)

    def test_warns_when_optional_configs_missing(self):
        self._create_email(ses=True)
        out, _ = self._run()
        self.assertIn("SMSServiceConfig", out)
        self.assertIn("GoogleCredentialConfig", out)
        self.assertIn("WARN", out)

    def test_strict_with_require_sms_fails_when_sms_missing(self):
        self._create_email(ses=True)
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-sms")

    def test_strict_with_require_sms_passes_when_configured(self):
        self._create_email(ses=True)
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
        )
        SMSServiceConfig.objects.create(
            name="SMS",
            is_active=True,
            from_number="+12065550000",
        )
        out, _ = self._run("--strict", "--require-sms")
        self.assertIn("passed", out)

    def test_strict_with_require_google_fails_without_google(self):
        self._create_email(ses=True)
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-google")

    def test_strict_with_require_google_passes_when_configured(self):
        self._create_email(ses=True)
        GoogleCredentialConfig.objects.create(
            name="Sheets",
            is_active=True,
            credentials_json=VALID_GOOGLE_JSON,
        )
        out, _ = self._run("--strict", "--require-google")
        self.assertIn("passed", out)

    def test_smtp_only_email_is_sufficient(self):
        self._create_email(ses=False)
        out, _ = self._run("--strict")
        self.assertIn("passed", out)

    def test_require_aws_fails_when_no_aws_config_and_no_ses(self):
        self._create_email(ses=False)
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-aws")
