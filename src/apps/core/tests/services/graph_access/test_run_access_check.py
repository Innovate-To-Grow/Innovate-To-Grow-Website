"""``run_access_check``: which Graph requests the check makes, and how each answer becomes PASS, FAIL, WARN, SKIP or
INCONCLUSIVE, adding up to the verdict."""

import base64
import email
import email.policy
import json

from django.test import TestCase, override_settings

from apps.core.models import MicrosoftGraphMailboxScope
from apps.core.services.email.graph import transport
from apps.core.services.email.graph.access_check import PROBE_SUBJECT, run_access_check
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph.provider.test_email_graph import token_response
from apps.core.tests.services.graph_access.helpers import (
    APA_MESSAGE,
    DENY,
    EXTRA_ROLES,
    MESSAGE_ID,
    SCOPED,
    ProbeFixtureMixin,
    Verdict,
    jwt,
    outcomes,
)

Permission = MicrosoftGraphMailboxScope.Permission
GUID = "6233fba6-1111-2222-3333-444455556666"
EVERYTHING_PASSES = [
    ("PASS", "token", "-"),
    ("PASS", "roles", "-"),
    ("PASS", "folder", SCOPED),
    ("PASS", "list", SCOPED),
    ("PASS", "value", SCOPED),
    ("PASS", "send", SCOPED),
    ("PASS", "folder", DENY),
    ("PASS", "list", DENY),
    ("PASS", "send", DENY),
    ("PASS", "sendas", SCOPED),
]


def apa_denied():
    body = json.dumps({"error": {"code": "ErrorAccessDenied", "message": APA_MESSAGE}}).encode()
    return HttpResponse(403, {}, body)


class _AccessCheckRunCase(ProbeFixtureMixin, TestCase):
    def run_check(self, **kwargs):
        return run_access_check(self.config, deny_mailbox=DENY, **kwargs)


class AccessCheckRunTests(_AccessCheckRunCase):
    def test_a_correct_restriction_with_approved_roles_matches_the_approval(self):
        report = self.run_check()

        self.assertEqual(outcomes(report), EVERYTHING_PASSES)
        self.assertEqual(report.verdict, Verdict.COMPLIANT)
        self.assertTrue(report.restriction_holds and report.complete)
        self.assertIs(report.roles_within_approval, True)
        self.assertEqual(report.granted_roles, ("Mail.ReadWrite", "Mail.Send"))
        self.assertEqual(report.certificate_sha1, self.config.current_certificate.sha1_thumbprint)
        self.assertIn("Verdict: MATCHES THE APPROVAL", report.summary())
        self.assertIn("matches the approval", report.conclusion())

    def test_the_requests_reach_only_graph_with_the_token_and_the_expected_paths(self):
        self.run_check()

        calls = self.probe.graph_calls()
        self.assertEqual({call[1] for call in calls}, {transport.GRAPH_HOST})
        self.assertEqual(
            [(call[0], call[2].split("?")[0]) for call in calls],
            [
                ("GET", f"/v1.0/users/{SCOPED}/mailFolders/inbox"),
                ("GET", f"/v1.0/users/{SCOPED}/mailFolders/inbox/messages"),
                ("GET", f"/v1.0/users/{SCOPED}/messages/{MESSAGE_ID}/$value"),
                ("POST", f"/v1.0/users/{SCOPED}/sendMail"),
                ("GET", f"/v1.0/users/{DENY}/mailFolders/inbox"),
                ("GET", f"/v1.0/users/{DENY}/mailFolders/inbox/messages"),
                ("POST", f"/v1.0/users/{DENY}/sendMail"),
                ("POST", f"/v1.0/users/{SCOPED}/sendMail"),
            ],
        )
        self.assertIn("$top=1&$select=id,bodyPreview", calls[1][2])
        for call in calls:
            self.assertTrue(call[4]["Authorization"].startswith("Bearer "))
            self.assertTrue(transport.is_allowed(call[0], call[1], call[2]))

    @override_settings(GRAPH_ACCESS_CHECK_MIME_MAX_BYTES=512)
    def test_the_raw_message_read_is_bounded_by_the_setting(self):
        self.run_check()

        value_call = next(call for call in self.probe.graph_calls() if call[2].endswith("/$value"))
        self.assertEqual(value_call[3], 512)

    def test_a_fresh_token_is_requested_even_when_one_is_cached(self):
        self.run_check()
        self.run_check()

        token_requests = [call for call in self.probe.calls if call[1] != transport.GRAPH_HOST]
        self.assertEqual(len(token_requests), 2)

    def test_the_allowed_send_is_mime_and_the_refused_sends_are_json_without_a_sent_items_copy(self):
        self.run_check()

        allowed, as_deny, send_as = [call for call in self.probe.graph_calls() if call[0] == "POST"]
        self.assertEqual(allowed[4]["Content-Type"], "text/plain")
        mime = email.message_from_bytes(base64.b64decode(allowed[3]), policy=email.policy.default)
        self.assertEqual((str(mime["From"]), str(mime["To"])), (SCOPED, SCOPED))
        self.assertEqual(str(mime["Subject"]), PROBE_SUBJECT)
        for call in (as_deny, send_as):
            body = json.loads(call[3])
            self.assertEqual(call[4]["Content-Type"], "application/json")
            self.assertIs(body["saveToSentItems"], False)
            self.assertEqual(body["message"]["from"]["emailAddress"]["address"], DENY)
            self.assertEqual([r["emailAddress"]["address"] for r in body["message"]["toRecipients"]], [SCOPED])

    def test_a_role_beyond_the_approved_ones_does_not_match(self):
        # Every mailbox probe passes, yet the token claims a role nobody approved.
        self.use_roles(EXTRA_ROLES)

        report = self.run_check()

        self.assertEqual(outcomes(report)[1], ("FAIL", "roles", "-"))
        self.assertTrue(report.restriction_holds)
        self.assertIs(report.roles_within_approval, False)
        self.assertEqual(report.verdict, Verdict.NOT_COMPLIANT)
        self.assertIn("BEYOND the approval (User.Read.All)", report.summary())
        self.assertIn("does NOT match the approval", report.conclusion())

    def test_an_infosec_exception_reference_accepts_extra_roles_and_says_so(self):
        self.use_roles(EXTRA_ROLES)
        self.config.permission_exception_reference = "RITM0450999"
        self.config.save()

        report = self.run_check()

        self.assertEqual(outcomes(report)[1], ("WARN", "roles", "-"))
        self.assertEqual(report.verdict, Verdict.COMPLIANT)
        self.assertIn("covered by InfoSec exception RITM0450999", report.conclusion())

    def test_no_roles_in_the_token_warn_but_still_match(self):
        self.use_roles(())

        report = self.run_check()

        self.assertEqual(outcomes(report)[1], ("WARN", "roles", "-"))
        self.assertEqual(report.verdict, Verdict.COMPLIANT)
        self.assertIn("NONE in the token", report.summary())

    def test_unreadable_roles_make_the_run_incomplete(self):
        self.probe.token = token_response(token=jwt({"roles": "Mail.ReadWrite"}))

        report = self.run_check()

        self.assertEqual(outcomes(report)[1], ("INCONCLUSIVE", "roles", "-"))
        self.assertIsNone(report.roles_within_approval)
        self.assertEqual(report.verdict, Verdict.INCOMPLETE)
        self.assertTrue(report.conclusion().startswith("NOT A COMPLETE VALIDATION"))
