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
from apps.core.tests.graph_helpers import grant
from apps.core.tests.services.graph_access.helpers import (
    ALLOW,
    APA_MESSAGE,
    DENIED,
    DENY,
    EMPTY_LIST,
    MESSAGE_ID,
    OIT_ROLES,
    REQUEST_ID,
    SCOPED,
    ProbeFixtureMixin,
    Verdict,
    jwt,
    outcomes,
)
from apps.core.tests.services.test_email_graph import error_body, token_response

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


class AccessCheckRunTests(ProbeFixtureMixin, TestCase):
    def run_check(self, **kwargs):
        return run_access_check(self.config, deny_mailbox=DENY, **kwargs)

    def test_a_correct_restriction_with_approved_roles_matches_the_approval(self):
        report = self.run_check()

        self.assertEqual(outcomes(report), EVERYTHING_PASSES)
        self.assertEqual(report.verdict, Verdict.COMPLIANT)
        self.assertTrue(report.restriction_holds and report.complete)
        self.assertIs(report.roles_within_approval, True)
        self.assertEqual(report.granted_roles, ("Mail.Read", "Mail.Send"))
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

    def test_mail_readwrite_in_the_token_does_not_match_the_approval(self):
        # The case OIT reportedly configured: every mailbox probe passes, yet the grant exceeds the approval.
        self.use_roles(OIT_ROLES)

        report = self.run_check()

        self.assertEqual(outcomes(report)[1], ("FAIL", "roles", "-"))
        self.assertTrue(report.restriction_holds)
        self.assertIs(report.roles_within_approval, False)
        self.assertEqual(report.verdict, Verdict.NOT_COMPLIANT)
        self.assertIn("BEYOND the approval (Mail.ReadWrite)", report.summary())
        self.assertIn("does NOT match the approval", report.conclusion())

    def test_an_infosec_exception_reference_accepts_extra_roles_and_says_so(self):
        self.use_roles(OIT_ROLES)
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

    def test_a_refused_message_list_on_a_read_scope_fails_and_skips_opening_a_message(self):
        self.probe.answer(SCOPED, "list", DENIED)

        report = self.run_check()

        self.assertIn(("FAIL", "list", SCOPED), outcomes(report))
        self.assertIn(("SKIP", "value", SCOPED), outcomes(report))
        self.assertEqual(report.verdict, Verdict.NOT_COMPLIANT)
        self.assertFalse(report.restriction_holds)

    def test_an_empty_inbox_leaves_opening_a_message_unexercised_so_the_run_is_incomplete(self):
        self.probe.answer(SCOPED, "list", EMPTY_LIST)

        report = self.run_check()

        value = next(result for result in report.results if result.check == "value")
        self.assertEqual(value.outcome, "INCONCLUSIVE")
        self.assertIn("($value) was not exercised", value.note)
        self.assertFalse(report.complete)
        self.assertEqual(report.verdict, Verdict.INCOMPLETE)

    def test_refusals_without_a_matching_allowed_request_are_inconclusive(self):
        # An app that may do nothing gets 403 everywhere: that is not evidence of a working restriction.
        for kind in ("folder", "list", "send"):
            self.probe.answer(SCOPED, kind, DENIED)

        report = self.run_check()

        for check in ("folder", "list", "send"):
            denial = next(r for r in report.results if r.check == check and r.mailbox == DENY)
            self.assertEqual(denial.outcome, "INCONCLUSIVE")
            self.assertIn(f"no {check} request for a scoped mailbox succeeded", denial.note)
        send_as = next(r for r in report.results if r.check == "sendas")
        self.assertEqual(send_as.outcome, "INCONCLUSIVE")
        self.assertEqual(report.verdict, Verdict.NOT_COMPLIANT)

    def test_granted_deny_access_fails_and_keeps_the_warning(self):
        self.probe.answer(DENY, "folder", ALLOW["folder"])
        self.probe.answer(DENY, "send", ALLOW["send"])
        self.probe.answer(SCOPED, "send", ALLOW["send"])

        results = {(r.check, r.mailbox): r for r in self.run_check().results}

        self.assertEqual(results[("folder", DENY)].outcome, "FAIL")
        self.assertIn("ACCESS WAS GRANTED", results[("folder", DENY)].note)
        send = results[("send", DENY)]
        self.assertEqual(send.outcome, "FAIL")
        self.assertIn("ACCESS WAS GRANTED", send.note)
        self.assertIn(f"a probe email was sent to {SCOPED} (no Sent Items copy)", send.note)
        send_as = results[("sendas", SCOPED)]
        self.assertEqual(send_as.outcome, "FAIL")
        self.assertIn(f"{SCOPED} may send as {DENY}", send_as.note)

    def test_an_access_policy_refusal_is_noted_and_the_request_id_kept(self):
        self.probe.answer(DENY, "folder", apa_denied())

        results = {(r.check, r.mailbox): r for r in self.run_check().results}

        folder = results[("folder", DENY)]
        self.assertEqual((folder.outcome, folder.code), ("PASS", "ErrorAccessDenied"))
        self.assertIn("as an Exchange Application Access Policy refuses", folder.note)
        self.assertNotIn("RAOP", folder.note)
        self.assertEqual(results[("list", DENY)].request_id, REQUEST_ID)
        self.assertNotIn("Exchange Application Access Policy", results[("list", DENY)].note)

    def test_a_missing_deny_mailbox_fails_with_a_note(self):
        self.probe.answer(DENY, "folder", HttpResponse(404, {}, error_body("ErrorInvalidUser")))

        folder = next(r for r in self.run_check().results if r.check == "folder" and r.mailbox == DENY)

        self.assertEqual((folder.outcome, folder.status, folder.code), ("FAIL", 404, "ErrorInvalidUser"))
        self.assertIn("mailbox not found", folder.note)

    def test_no_send_skips_every_send_and_is_not_a_complete_validation(self):
        report = self.run_check(send=False)

        self.assertEqual(
            [(outcome, check) for outcome, check, _mailbox in outcomes(report) if "send" in check],
            [("SKIP", "send"), ("SKIP", "send"), ("SKIP", "sendas")],
        )
        self.assertFalse(any(call[0] == "POST" for call in self.probe.graph_calls()))
        self.assertEqual(report.verdict, Verdict.INCOMPLETE)
        self.assertIn("NOT PROVEN", report.summary())

    def test_a_scope_without_any_send_permission_skips_the_send_probes(self):
        self.config.mailbox_scopes.update(permission=Permission.READ)

        report = self.run_check()

        self.assertIn(("SKIP", "send", "-"), outcomes(report))
        self.assertIn(("SKIP", "sendas", "-"), outcomes(report))
        self.assertEqual(report.verdict, Verdict.INCOMPLETE)

    def test_a_scope_without_any_read_permission_skips_the_read_probes_and_records_the_extra_read(self):
        self.config.mailbox_scopes.update(permission=Permission.SEND)

        report = self.run_check()

        self.assertIn(("SKIP", "folder", "-"), outcomes(report))
        extra = next(r for r in report.results if r.check == "read+")
        self.assertEqual((extra.outcome, extra.mailbox, extra.expected), ("WARN", SCOPED, "not in scope"))
        self.assertIn("only the site's scope stops it", extra.note)
        self.assertEqual(report.verdict, Verdict.INCOMPLETE)

    def test_microsoft_refusing_the_extra_read_passes_it(self):
        self.config.mailbox_scopes.update(permission=Permission.SEND)
        grant(self.config, "reader@contoso.com", permission=Permission.READ)
        self.probe.answer(SCOPED, "folder", DENIED)

        report = self.run_check()

        extra = next(r for r in report.results if r.check == "read+")
        self.assertEqual(extra.outcome, "PASS")
        self.assertIn("refuses reading this send-only mailbox too", extra.note)
        self.assertEqual(report.verdict, Verdict.COMPLIANT)

    def test_a_mailbox_listed_by_object_id_is_not_used_for_sending(self):
        self.config.mailbox_scopes.update(permission=Permission.READ)
        grant(self.config, GUID, permission=Permission.SEND)

        report = self.run_check()

        self.assertIn(("SKIP", "send", GUID), outcomes(report))
        self.assertFalse(any(GUID in str(call[3]) for call in self.probe.graph_calls() if call[0] == "POST"))
        self.assertEqual(report.verdict, Verdict.INCOMPLETE)

    def test_the_refused_sends_go_to_the_sender_mailbox(self):
        # Listed before the sender mailbox, so only the preference for the sender makes it the recipient.
        grant(self.config, "another@contoso.com", permission=Permission.SEND)

        self.run_check()

        as_deny = [call for call in self.probe.graph_calls() if call[0] == "POST" and DENY in call[2]][0]
        recipients = json.loads(as_deny[3])["message"]["toRecipients"]
        self.assertEqual([r["emailAddress"]["address"] for r in recipients], [SCOPED])

    def test_mailboxes_that_would_change_the_url_are_refused_before_any_connection(self):
        grant(self.config, "a/b?c@contoso.com", permission=Permission.READ)

        results = [r for r in self.run_check().results if r.mailbox == "a/b?c@contoso.com"]

        self.assertEqual([r.outcome for r in results[:2]], ["FAIL", "FAIL"])
        self.assertIn("The site does not make this Microsoft Graph request.", results[0].note)
        self.assertFalse(any("a%2Fb" in call[2] or "a/b" in call[2] for call in self.probe.graph_calls()))

    def test_unreachable_graph_fails_the_probe(self):
        self.probe.answer(SCOPED, "folder", transport.ConnectFailed())
        self.probe.answer(SCOPED, "send", transport.ResponseLost())

        results = {(r.check, r.mailbox): r for r in self.run_check().results}

        self.assertEqual(results[("folder", SCOPED)].note, "Graph could not be reached.")
        self.assertIn("a probe email may have been sent", results[("send", SCOPED)].note)

    def test_a_token_failure_stops_before_any_graph_request(self):
        self.probe.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')

        report = self.run_check()

        self.assertEqual(outcomes(report), [("FAIL", "token", "-")])
        self.assertTrue(report.results[0].note)
        self.assertIsNone(report.granted_roles)
        self.assertEqual(report.verdict, Verdict.NOT_COMPLIANT)
        self.assertEqual(self.probe.graph_calls(), [])
