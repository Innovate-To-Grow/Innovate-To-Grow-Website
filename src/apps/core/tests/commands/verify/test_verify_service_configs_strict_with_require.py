from django.core.management import CommandError

from apps.core.models import (
    GoogleCredentialConfig,
)
from apps.core.tests.commands.verify.test_verify_service_configs import (
    VALID_GOOGLE_JSON,
    _VerifyServiceConfigsCommandCase,
)


class VerifyServiceConfigsCommandTest(_VerifyServiceConfigsCommandCase):
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
