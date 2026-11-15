import datetime
from io import StringIO

from django.core.management import CommandError, call_command

from apps.core.models import (
    MicrosoftGraphCertificate,
    SMTPProviderConfig,
)
from apps.core.tests.commands.graph.test_graph_verify_service_configs import (
    CLIENT_ID,
    FROM,
    NO_CERTIFICATE,
    NO_SCOPE,
    NOT_IN_SCOPE,
    TENANT_ID,
    Permission,
    _VerifyServiceConfigsGraphScopeCase,
)
from apps.core.tests.graph_helpers import create_graph_config


class VerifyServiceConfigsGraphScopeTest(_VerifyServiceConfigsGraphScopeCase):
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
