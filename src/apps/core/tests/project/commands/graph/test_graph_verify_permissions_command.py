"""``manage.py verify_graph_access --permissions-only``: the token's roles, the capability table and the Message Trace
probe; a recorded ``MicrosoftGraphPermissionCheck``, never an access check; exit 1 only without a token."""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphPermissionCheck, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.access_check import permissions
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph.tracing import (
    TRACE_ROLE,
    TraceSetupMixin,
    token_response,
    token_with_roles,
    trace_page,
)

OIT_ROLES = ("Mail.ReadWrite", "Mail.Send")


class VerifyGraphPermissionsCommandTests(TraceSetupMixin, TestCase):
    message_trace = False

    def run_command(self):
        out = StringIO()
        call_command("verify_graph_access", "--permissions-only", stdout=out, stderr=StringIO(), no_color=True)
        return out.getvalue()

    def use_roles(self, roles):
        self.microsoft.token = token_response(token=token_with_roles(roles))

    def test_todays_roles_print_approved_with_the_capabilities_and_trace_not_granted(self):
        self.use_roles(OIT_ROLES)

        output = self.run_command()

        check = MicrosoftGraphPermissionCheck.objects.get()
        for line in (
            f"Certificate: SHA-1 {self.config.current_certificate.sha1_thumbprint}",
            "Token: issued with the current certificate",
            "Granted application roles:\n",
            "  Mail.ReadWrite",
            "[yes] Send mail (Mail.Send)",
            "[yes] Bounce scan, admin inbox and helpdesk reading (Mail.Read or Mail.ReadWrite)",
            f"[ no] Message Trace delivery status ({TRACE_ROLE})",
            "Message Trace: Not granted (not probed).",
            permissions.CAVEAT,
            f"Recorded as permission check {check.pk}.",
        ):
            self.assertIn(line, output)
        self.assertNotIn("BEYOND", output)
        self.assertEqual(self.microsoft.traces, [])
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())

    def test_the_trace_role_is_probed_and_flagged_beyond_the_approval(self):
        self.use_roles((*OIT_ROLES, TRACE_ROLE))

        output = self.run_command()

        self.assertIn(f"  {TRACE_ROLE:<40} BEYOND the approval", output)
        self.assertIn(permissions.RECORD_REFERENCE_FIRST, output)
        self.assertIn("Message Trace: Available.", output)
        self.assertEqual(len(self.microsoft.traces), 1)

    def test_a_refused_trace_still_exits_zero(self):
        self.use_roles((*OIT_ROLES, TRACE_ROLE))
        self.microsoft.pages = [trace_page(status=401, body=b"{}")]

        output = self.run_command()

        self.assertIn("Message Trace: Service principal missing or still provisioning.", output)
        self.assertIn(permissions.TRACE_APP_ID, output)

    def test_no_token_exits_one_and_is_recorded(self):
        self.microsoft.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')

        with self.assertRaisesMessage(CommandError, "No token was issued"):
            self.run_command()

        self.assertFalse(MicrosoftGraphPermissionCheck.objects.get().token_ok)

    def test_without_an_active_config_nothing_is_requested(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)

        with self.assertRaisesMessage(CommandError, "No active Microsoft Graph provider config."):
            self.run_command()

        self.assertEqual(self.microsoft.requests, [])
