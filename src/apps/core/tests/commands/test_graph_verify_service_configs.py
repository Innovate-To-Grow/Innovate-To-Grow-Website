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
    MicrosoftGraphMailboxScope,
    MicrosoftGraphProviderConfig,
    SMTPProviderConfig,
)
from apps.core.tests.graph_helpers import certificate_pair, create_graph_config, grant

Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FROM = "i2g@g.ucmerced.edu"
SECRET_WARNING = "authenticates with a client secret, not a certificate"
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

    def secret_graph(self, scope=(FROM,), **overrides):
        values = {"name": "Graph", "is_active": True, "tenant_id": TENANT_ID, "client_id": CLIENT_ID}
        return create_graph_config(scope=scope, **{**values, "client_secret": "not-a-real-secret", **overrides})

    def certificate_graph(self, days_valid=365, scope=(FROM,)):
        certificate, key = certificate_pair(days_valid=days_valid)
        return create_graph_config(
            scope=scope,
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            auth_method=MicrosoftGraphProviderConfig.AuthMethod.CERTIFICATE,
            certificate=certificate,
            private_key=key,
        )

    def expire(self, config, delta):
        MicrosoftGraphProviderConfig.objects.filter(pk=config.pk).update(certificate_expires_at=timezone.now() + delta)

    def test_a_valid_certificate_passes_strict_without_auth_warnings(self):
        self.email()
        self.certificate_graph()

        out = self.run_command("--strict")

        self.assertIn("MicrosoftGraphProviderConfig: OK", out)
        self.assertIn("Service config verification passed.", out)
        self.assertNotIn(SECRET_WARNING, out)
        self.assertNotIn("certificate expires", out)

    def test_client_secret_auth_warns(self):
        self.email()
        self.secret_graph()

        out = self.run_command("--strict")

        self.assertIn(f"WARN: MicrosoftGraphProviderConfig {SECRET_WARNING}.", out)
        self.assertIn("Service config verification passed.", out)

    def test_a_certificate_expiring_within_30_days_warns(self):
        self.email()
        self.expire(self.certificate_graph(), datetime.timedelta(days=10, hours=1))

        out = self.run_command("--strict")

        self.assertIn("WARN: The Microsoft Graph certificate expires on", out)
        self.assertIn("(10 days); rotate it.", out)
        self.assertIn("Service config verification passed.", out)

    def test_a_certificate_with_more_than_30_days_left_is_quiet(self):
        self.email()
        self.expire(self.certificate_graph(), datetime.timedelta(days=31))

        self.assertNotIn("rotate it", self.run_command("--strict"))

    def test_an_expired_certificate_fails_when_graph_is_the_provider(self):
        self.email()
        self.expire(self.certificate_graph(), -datetime.timedelta(days=2))
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
        self.expire(self.certificate_graph(), -datetime.timedelta(hours=1))

        out = self.run_command("--strict")

        self.assertIn("WARN: The Microsoft Graph certificate expired on", out)
        self.assertIn("Service config verification passed.", out)

    def test_missing_scope_fails_when_graph_is_the_provider(self):
        self.email()
        self.secret_graph(scope=())

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
        self.secret_graph(scope=())

        out = self.run_command("--strict")

        self.assertIn(f"WARN: MicrosoftGraphProviderConfig {NO_SCOPE}.", out)
        self.assertNotIn("MicrosoftGraphProviderConfig: ", out)

    def test_a_from_address_outside_the_scope_fails(self):
        self.email()
        self.secret_graph(scope=("other@g.ucmerced.edu",))

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
            client_secret="not-a-real-secret",
        )

        with self.assertRaises(CommandError):
            self.run_command("--strict")

    def test_a_certificate_row_without_a_pair_fails_without_expiry_messages(self):
        """An active certificate row that skipped validation (bulk insert) has no recorded expiry."""
        self.email()
        row = MicrosoftGraphProviderConfig(
            name="Broken", is_active=True, tenant_id=TENANT_ID, client_id=CLIENT_ID, auth_method="certificate"
        )
        MicrosoftGraphProviderConfig.objects.bulk_create([row])
        grant(row, FROM)

        out = self.run_command()

        self.assertIn("MicrosoftGraphProviderConfig: MISSING", out)
        self.assertNotIn("certificate expire", out)
        self.assertNotIn(SECRET_WARNING, out)

    def test_an_inactive_graph_config_is_not_checked(self):
        self.email(provider="smtp")
        SMTPProviderConfig.objects.create(
            name="SMTP", is_active=True, host="smtp.example.com", port=587, username="u", password="not-a-real-pw"
        )
        self.secret_graph(scope=(), is_active=False)

        out = self.run_command("--strict")

        self.assertNotIn("Graph", out)
        self.assertIn("Service config verification passed.", out)
