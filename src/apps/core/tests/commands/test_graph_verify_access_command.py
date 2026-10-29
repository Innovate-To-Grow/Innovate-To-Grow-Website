"""``manage.py verify_graph_access``: argument checks, the report, and the exit status."""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.test_graph_access_check import (
    ALLOW_READ,
    DENY,
    SCOPED,
    ProbeFixtureMixin,
)


class VerifyGraphAccessCommandTests(ProbeFixtureMixin, TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("verify_graph_access", *args, stdout=out, stderr=StringIO(), no_color=True)
        return out.getvalue()

    def test_passes_when_the_tenant_matches_the_scope(self):
        output = self.run_command("--deny-mailbox", DENY)

        self.assertEqual(output.count("PASS"), 5)
        self.assertNotIn("FAIL", output)
        self.assertIn(f"probe email sent to {SCOPED}", output)
        self.assertIn("matches the approved mailbox scope", output)

    def test_deny_mailbox_is_normalized(self):
        output = self.run_command("--deny-mailbox", "  Intruder-Test@Contoso.com ")

        self.assertIn(DENY, output)
        self.assertEqual(output.count("PASS"), 5)

    def test_no_send_skips_the_send_probes(self):
        output = self.run_command("--deny-mailbox", DENY, "--no-send")

        self.assertEqual(output.count("PASS"), 3)
        self.assertNotIn("send ", output)
        self.assertFalse(any(call[0] == "POST" for call in self.probe.graph_calls()))

    def test_any_failure_raises_after_printing_the_report(self):
        self.probe.answer("GET", DENY, ALLOW_READ)
        out = StringIO()

        with self.assertRaisesMessage(CommandError, "does not match the approved scope"):
            call_command("verify_graph_access", "--deny-mailbox", DENY, stdout=out, no_color=True)

        self.assertIn("FAIL  read", out.getvalue())
        self.assertIn("ACCESS WAS GRANTED", out.getvalue())

    def test_a_token_failure_is_reported_and_fails(self):
        self.probe.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command("verify_graph_access", "--deny-mailbox", DENY, stdout=out, no_color=True)
        self.assertIn("FAIL  token", out.getvalue())
        self.assertIn("got -", out.getvalue())

    def test_refuses_a_deny_mailbox_inside_the_scope(self):
        with self.assertRaisesMessage(CommandError, "inside the configured scope"):
            self.run_command("--deny-mailbox", SCOPED.upper())
        self.assertEqual(self.probe.calls, [])

    def test_refuses_a_malformed_deny_mailbox(self):
        with self.assertRaisesMessage(CommandError, "must be a mailbox address"):
            self.run_command("--deny-mailbox", "not a mailbox")
        self.assertEqual(self.probe.calls, [])

    def test_refuses_when_graph_is_not_configured(self):
        for label, change in {
            "inactive": lambda: MicrosoftGraphProviderConfig.objects.update(is_active=False),
            "no scope": lambda: self.config.mailbox_scopes.all().delete(),
            "no config": lambda: MicrosoftGraphProviderConfig.objects.all().delete(),
        }.items():
            with self.subTest(label):
                change()
                with self.assertRaisesMessage(CommandError, "No active, fully configured"):
                    self.run_command("--deny-mailbox", DENY)
        self.assertEqual(self.probe.calls, [])

    def test_deny_mailbox_is_required(self):
        with self.assertRaises(CommandError):
            self.run_command()
