"""``manage.py verify_graph_access``: arguments, the evidence header, each probe line, the verdict, the exit status
and the recorded ``MicrosoftGraphAccessCheck`` row."""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.access_check.runner import DENY_MAILBOX_IN_USE, INVALID_DENY_MAILBOX
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph_access.helpers import (
    ALLOW,
    DENIED,
    DENY,
    OIT_ROLES,
    REQUEST_ID,
    SCOPED,
    ProbeFixtureMixin,
    Verdict,
)

SUCCESS = "Microsoft Graph access matches the approval"
INCOMPLETE = "NOT A COMPLETE VALIDATION"


class VerifyGraphAccessCommandTests(ProbeFixtureMixin, TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("verify_graph_access", *args, stdout=out, stderr=StringIO(), no_color=True)
        return out.getvalue()

    def run_failing(self, *args, message=""):
        out = StringIO()
        with self.assertRaisesMessage(CommandError, message):
            call_command("verify_graph_access", *args, stdout=out, stderr=StringIO(), no_color=True)
        return out.getvalue()

    def test_a_matching_run_prints_the_evidence_and_records_it(self):
        output = self.run_command()

        check = MicrosoftGraphAccessCheck.objects.get()
        certificate = self.config.current_certificate
        for line in (
            f"Entra app: tenant {self.config.tenant_id}, client {self.config.client_id}",
            f"Authentication: certificate only; SHA-1 {certificate.sha1_thumbprint}, "
            f"key version {certificate.store_version_id}",
            f"Deny mailbox: {DENY}\n",
            "Approved application roles: Mail.Read, Mail.Send",
            "InfoSec exception: none recorded",
            "Mailbox restriction: HOLDS · Granted roles: WITHIN the approval · Verdict: MATCHES THE APPROVAL",
            "can take more than an hour to apply",
            SUCCESS,
            f"Recorded as access check {check.pk}.",
            "Go-live evidence: present",
        ):
            self.assertIn(line, output)
        self.assertEqual(output.count("\nPASS "), 10)
        self.assertIn(f"[request-id {REQUEST_ID}]", output)
        self.assertEqual((check.verdict, check.source), (Verdict.COMPLIANT, MicrosoftGraphAccessCheck.Source.COMMAND))

    def test_the_deny_mailbox_defaults_to_the_designated_one_and_can_be_overridden(self):
        other = "other-test@contoso.com"
        for kind in ("folder", "list", "send"):
            self.probe.answer(other, kind, DENIED)

        output = self.run_command("--deny-mailbox", f"  {other.upper()} ")

        self.assertIn(f"Deny mailbox: {other} (not the designated Access Check Deny Mailbox", output)
        self.assertEqual(MicrosoftGraphAccessCheck.objects.get().deny_mailbox, other)
        self.assertIn("Go-live evidence: missing: the latest access check did not use the designated", output)

    def test_mail_readwrite_in_the_token_fails_even_though_every_mailbox_probe_passes(self):
        self.use_roles(OIT_ROLES)

        output = self.run_failing(message="does NOT match the approval")

        self.assertIn("FAIL         roles", output)
        self.assertIn("beyond the approval: Mail.ReadWrite", output)
        self.assertIn("Mailbox restriction: HOLDS · Granted roles: BEYOND the approval (Mail.ReadWrite)", output)
        self.assertNotIn(SUCCESS, output)
        self.assertEqual(MicrosoftGraphAccessCheck.objects.get().verdict, Verdict.NOT_COMPLIANT)

    def test_an_infosec_exception_reference_lets_the_run_pass_and_is_printed(self):
        self.use_roles(OIT_ROLES)
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(
            permission_exception_reference="RITM0450999"
        )

        output = self.run_command()

        self.assertIn("InfoSec exception: RITM0450999", output)
        self.assertIn("covered by InfoSec exception RITM0450999", output)

    def test_no_send_is_not_a_complete_validation_and_fails(self):
        output = self.run_failing("--no-send", message=INCOMPLETE)

        self.assertIn("SKIP         send", output)
        self.assertIn(INCOMPLETE, output)
        self.assertNotIn(SUCCESS, output)
        self.assertFalse(any(call[0] == "POST" for call in self.probe.graph_calls()))
        self.assertEqual(MicrosoftGraphAccessCheck.objects.get().verdict, Verdict.INCOMPLETE)

    def test_granted_deny_access_fails_with_the_warning(self):
        self.probe.answer(DENY, "folder", ALLOW["folder"])

        output = self.run_failing(message="does NOT match the approval")

        self.assertIn("FAIL         folder", output)
        self.assertIn("ACCESS WAS GRANTED", output)

    def test_a_token_failure_is_reported_and_recorded(self):
        self.probe.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')

        output = self.run_failing()

        self.assertIn("FAIL         token", output)
        self.assertIn("got -", output)
        self.assertEqual(MicrosoftGraphAccessCheck.objects.get().verdict, Verdict.NOT_COMPLIANT)

    def test_refuses_a_deny_mailbox_that_is_in_use_or_malformed_before_any_request(self):
        for value, message in ((SCOPED.upper(), DENY_MAILBOX_IN_USE), ("not a mailbox", INVALID_DENY_MAILBOX)):
            with self.subTest(value=value):
                self.run_failing("--deny-mailbox", value, message=message)
        self.assertEqual(self.probe.calls, [])
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())

    def test_refuses_without_a_designated_or_given_deny_mailbox(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(access_check_deny_mailbox="")

        self.run_failing(message="Set the Access Check Deny Mailbox")
        self.assertEqual(self.probe.calls, [])

    def test_refuses_when_graph_is_not_configured(self):
        for label, change in {
            "inactive": lambda: MicrosoftGraphProviderConfig.objects.update(is_active=False),
            "no scope": lambda: self.config.mailbox_scopes.all().delete(),
            "no config": lambda: MicrosoftGraphProviderConfig.objects.all().delete(),
        }.items():
            with self.subTest(label):
                change()
                self.run_failing(message="No active, fully configured")
        self.assertEqual(self.probe.calls, [])

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_a_matching_run_is_go_live_evidence_where_the_gate_is_on(self):
        output = self.run_command()

        self.assertIn("Go-live evidence: present", output)
