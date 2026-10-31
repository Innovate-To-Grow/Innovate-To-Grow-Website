"""verify_service_configs: Microsoft Graph mailbox scope, authentication method and certificate expiry checks."""

import datetime
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GoogleCredentialConfig,
    MicrosoftGraphCertificate,
    MicrosoftGraphMailboxScope,
    MicrosoftGraphProviderConfig,
    SMTPProviderConfig,
)
from apps.core.tests.graph_helpers import create_graph_config

Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FROM = "i2g@g.ucmerced.edu"
NO_CERTIFICATE = "MicrosoftGraphProviderConfig has no installed certificate."
NO_SCOPE = "has no mailbox scope; Graph refuses every mailbox"
NOT_IN_SCOPE = "not in the mailbox scope with send permission"


class VerifyServiceConfigsGraphScopeTest(TestCase):
    def setUp(self):
        for model in (
            EmailServiceConfig,
            GoogleCredentialConfig,
            AWSCredentialConfig,
            SMTPProviderConfig,
            MicrosoftGraphProviderConfig,
        ):
            model.objects.all().delete()
        patcher = patch("apps.core.services.aws.sms.origination_number_available", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args):
        out = StringIO()
        call_command("verify_service_configs", *args, stdout=out, stderr=StringIO(), no_color=True)
        return out.getvalue()

    def email(self, provider="graph"):
        return EmailServiceConfig.objects.create(name="Prod", is_active=True, provider=provider, from_email=FROM)

    def graph(self, scope=(FROM,), **overrides):
        values = {"name": "Graph", "is_active": True, "tenant_id": TENANT_ID, "client_id": CLIENT_ID}
        return create_graph_config(scope=scope, **{**values, **overrides})

    def expire(self, config, delta):
        MicrosoftGraphCertificate.objects.filter(config=config).update(not_after=timezone.now() + delta)

    def test_a_valid_certificate_passes_strict_quietly(self):
        self.email()
        self.graph()

        out = self.run_command("--strict")

        self.assertIn("MicrosoftGraphProviderConfig: OK", out)
        self.assertIn("Service config verification passed.", out)
        self.assertNotIn("Microsoft Graph certificate", out)
        self.assertNotIn("MicrosoftGraphProviderConfig has", out)

    def test_no_installed_certificate_fails_when_graph_is_the_provider(self):
        self.email()
        self.graph(certificate=False)

        out = self.run_command()

        self.assertIn(f"FAIL: {NO_CERTIFICATE}", out)
        self.assertNotIn("certificate expire", out)
        with self.assertRaises(CommandError):
            self.run_command("--strict")

    def test_a_certificate_that_is_not_valid_yet_fails(self):
        self.email()
        config = self.graph()
        start = timezone.now() + datetime.timedelta(days=2)
        MicrosoftGraphCertificate.objects.filter(config=config).update(not_before=start)

        out = self.run_command()

        self.assertIn(f"FAIL: The Microsoft Graph certificate is not valid until {start:%Y-%m-%d}.", out)
        self.assertIn("MicrosoftGraphProviderConfig: MISSING", out)

    def test_a_certificate_expiring_within_30_days_warns(self):
        self.email()
        self.expire(self.graph(), datetime.timedelta(days=10, hours=1))

        out = self.run_command("--strict")

        self.assertIn("WARN: The Microsoft Graph certificate expires on", out)
        self.assertIn("(10 days); rotate it.", out)
        self.assertIn("Service config verification passed.", out)

    def test_a_certificate_with_more_than_30_days_left_is_quiet(self):
        self.email()
        self.expire(self.graph(), datetime.timedelta(days=31))

        self.assertNotIn("rotate it", self.run_command("--strict"))

    def test_an_expired_certificate_fails_when_graph_is_the_provider(self):
        self.email()
        self.expire(self.graph(), -datetime.timedelta(days=2))
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command("verify_service_configs", "--strict", stdout=out, stderr=StringIO(), no_color=True)

        self.assertIn("FAIL: The Microsoft Graph certificate expired on", out.getvalue())
        self.assertIn("MicrosoftGraphProviderConfig: MISSING", out.getvalue())

    def test_an_expired_certificate_only_warns_when_graph_is_not_the_provider(self):
        self.email(provider="smtp")
        SMTPProviderConfig.objects.create(
            name="SMTP", is_active=True, host="smtp.example.com", port=587, username="u", password="not-a-real-pw"
        )
        self.expire(self.graph(), -datetime.timedelta(hours=1))

        out = self.run_command("--strict")

        self.assertIn("WARN: The Microsoft Graph certificate expired on", out)
        self.assertIn("Service config verification passed.", out)

    def test_missing_scope_fails_when_graph_is_the_provider(self):
        self.email()
        self.graph(scope=())

        out = self.run_command()

        self.assertIn(f"FAIL: MicrosoftGraphProviderConfig {NO_SCOPE}.", out)
        self.assertIn("MicrosoftGraphProviderConfig: MISSING", out)
        with self.assertRaises(CommandError):
            self.run_command("--strict")

    def test_missing_scope_warns_when_graph_is_not_the_provider(self):
        self.email(provider="smtp")
        SMTPProviderConfig.objects.create(
            name="SMTP", is_active=True, host="smtp.example.com", port=587, username="u", password="not-a-real-pw"
        )
        self.graph(scope=())

        out = self.run_command("--strict")

        self.assertIn(f"WARN: MicrosoftGraphProviderConfig {NO_SCOPE}.", out)
        self.assertNotIn("MicrosoftGraphProviderConfig: ", out)

    def test_a_from_address_outside_the_scope_fails(self):
        self.email()
        self.graph(scope=("other@g.ucmerced.edu",))

        out = self.run_command()

        self.assertIn(NOT_IN_SCOPE, out)
        self.assertIn("MicrosoftGraphProviderConfig: MISSING", out)

    def test_a_read_only_scope_cannot_send(self):
        self.email()
        create_graph_config(
            scope=(FROM,),
            permission=Permission.READ,
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
        )

        with self.assertRaises(CommandError):
            self.run_command("--strict")

    def test_removed_certificates_fail_without_expiry_messages(self):
        self.email()
        self.graph().certificates.update(state=MicrosoftGraphCertificate.State.REMOVED)

        out = self.run_command()

        self.assertIn("MicrosoftGraphProviderConfig: MISSING", out)
        self.assertIn(f"FAIL: {NO_CERTIFICATE}", out)
        self.assertNotIn("certificate expire", out)

    def test_an_inactive_graph_config_is_not_checked(self):
        self.email(provider="smtp")
        SMTPProviderConfig.objects.create(
            name="SMTP", is_active=True, host="smtp.example.com", port=587, username="u", password="not-a-real-pw"
        )
        self.graph(scope=(), is_active=False)

        out = self.run_command("--strict")

        self.assertNotIn("Graph", out)
        self.assertIn("Service config verification passed.", out)
