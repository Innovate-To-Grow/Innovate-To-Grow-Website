"""verify_service_configs with the Gmail API email provider."""

from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.core.tests.gmail_api_helpers import make_config, make_email_config


class VerifyServiceConfigsGmailTest(TestCase):
    def setUp(self):
        EmailServiceConfig.objects.all().delete()
        patcher = patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args):
        out = StringIO()
        call_command("verify_service_configs", *args, stdout=out, stderr=StringIO(), no_color=True)
        return out.getvalue()

    def test_a_ready_gmail_with_current_evidence_passes_the_email_check(self):
        make_config()
        make_email_config()
        output = self.run_command()
        self.assertIn("GmailApiProviderConfig: OK", output)
        self.assertIn("EmailServiceConfig: OK", output)
        self.assertNotIn("Gmail API:", output)

    def test_missing_evidence_after_a_rotation_fails_strict_while_gmail_is_selected(self):
        config = make_config()
        make_email_config()
        config.key_installed_at = timezone.now()
        config.save()
        output = self.run_command()
        self.assertIn("FAIL: Gmail API: no access check has passed for the installed key", output)
        self.assertIn("EmailServiceConfig: OK", output)  # sends still work: only the evidence is missing
        with self.assertRaises(CommandError):
            self.run_command("--strict")

    def test_a_from_address_off_the_list_fails(self):
        make_config()
        make_email_config(from_email="other@g.ucmerced.edu")
        output = self.run_command()
        self.assertIn("The From address is not on the Gmail API account allow-list.", output)
        self.assertIn("EmailServiceConfig selects the Gmail API, but GmailApiProviderConfig is not ready.", output)

    def test_an_unselected_configured_gmail_only_warns(self):
        config = make_config()
        make_email_config(provider=EmailServiceConfig.Provider.SES)
        config.subjects.all().delete()
        output = self.run_command()
        self.assertIn("WARN: GmailApiProviderConfig has an empty allow-list", output)
