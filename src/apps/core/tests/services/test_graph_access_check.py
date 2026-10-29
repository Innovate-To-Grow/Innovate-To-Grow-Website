"""``graph.access_check.run_access_check``: the probes that prove the tenant-side mailbox restriction.

``ProbeFake`` replaces both ``transport.post`` and ``transport.get`` and answers per mailbox, so no socket opens.
"""

import base64
import email
import email.policy
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import MicrosoftGraphMailboxScope
from apps.core.services.email.graph import auth, transport
from apps.core.services.email.graph.access_check import PROBE_SUBJECT, ProbeResult, run_access_check
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config, grant
from apps.core.tests.services.test_email_graph import (
    ACCESS_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET,
    TENANT_ID,
    error_body,
    token_response,
)

Permission = MicrosoftGraphMailboxScope.Permission
SCOPED = "i2g@contoso.com"
DENY = "intruder-test@contoso.com"
ALLOW_READ = HttpResponse(200, {}, b'{"id": "inbox"}')
ALLOW_SEND = HttpResponse(202, {}, b"")
DENIED = HttpResponse(403, {}, error_body("ErrorAccessDenied"))


class ProbeFake:
    """Answers token requests, then Graph per (method, mailbox): allowed for scoped mailboxes, 403 otherwise."""

    def __init__(self):
        self.token = token_response()
        self.answers = {}
        self.calls = []

    def answer(self, method, mailbox, response):
        self.answers[(method, mailbox)] = response

    def _respond(self, method, path):
        mailbox = path.split("/")[3]
        default = DENIED if mailbox == DENY else (ALLOW_READ if method == "GET" else ALLOW_SEND)
        outcome = self.answers.get((method, mailbox), default)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def post(self, host, path, body, headers, *, timeout):
        self.calls.append(("POST", host, path, body, headers))
        if host == auth.AUTHORITY_HOST:
            if isinstance(self.token, Exception):
                raise self.token
            return self.token
        return self._respond("POST", path)

    def get(self, host, path, headers, *, timeout, max_bytes):
        self.calls.append(("GET", host, path, None, headers))
        return self._respond("GET", path)

    def graph_calls(self):
        return [call for call in self.calls if call[1] != auth.AUTHORITY_HOST]


class ProbeFixtureMixin:
    def setUp(self):
        super().setUp()
        auth.clear_access_token_cache()
        self.addCleanup(auth.clear_access_token_cache)
        self.probe = ProbeFake()
        for name in ("post", "get"):
            patcher = patch(f"apps.core.services.email.graph.transport.{name}", new=getattr(self.probe, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.config = create_graph_config(
            scope=(SCOPED,),
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )


class RunAccessCheckTests(ProbeFixtureMixin, TestCase):
    def run_check(self, **kwargs):
        return run_access_check(self.config, deny_mailbox=DENY, **kwargs)

    def test_a_correct_tenant_restriction_passes_every_probe(self):
        results = self.run_check()

        self.assertEqual(
            [(r.check, r.mailbox, r.expected, r.status, r.passed) for r in results],
            [
                ("token", "-", "issued", 200, True),
                ("read", SCOPED, "allowed", 200, True),
                ("send", SCOPED, "allowed", 202, True),
                ("read", DENY, "denied (403)", 403, True),
                ("send", DENY, "denied (403)", 403, True),
            ],
        )
        self.assertEqual(results[2].note, f"probe email sent to {SCOPED}")
        self.assertEqual(results[3].code, "ErrorAccessDenied")

    def test_requests_use_the_token_and_the_expected_paths(self):
        self.run_check()

        paths = [(method, path) for method, _, path, _, _ in self.probe.graph_calls()]
        self.assertEqual(
            paths,
            [
                ("GET", f"/v1.0/users/{SCOPED}/mailFolders/inbox?$select=id"),
                ("POST", f"/v1.0/users/{SCOPED}/sendMail"),
                ("GET", f"/v1.0/users/{DENY}/mailFolders/inbox?$select=id"),
                ("POST", f"/v1.0/users/{DENY}/sendMail"),
            ],
        )
        for call in self.probe.graph_calls():
            self.assertEqual(call[4]["Authorization"], f"Bearer {ACCESS_TOKEN}")

    def test_the_deny_send_probe_is_addressed_to_a_scoped_mailbox(self):
        self.run_check()

        deny_send = self.probe.graph_calls()[-1]
        mime = email.message_from_bytes(base64.b64decode(deny_send[3]), policy=email.policy.default)
        self.assertEqual(str(mime["To"]), SCOPED)
        self.assertIn(DENY, str(mime["From"]))
        self.assertEqual(str(mime["Subject"]), PROBE_SUBJECT)

    def test_no_send_skips_every_send_probe(self):
        results = self.run_check(send=False)

        self.assertEqual([r.check for r in results], ["token", "read", "read"])
        self.assertFalse(any(call[0] == "POST" for call in self.probe.graph_calls()))

    def test_probes_follow_the_permission_level(self):
        self.config.mailbox_scopes.update(permission=Permission.SEND)
        grant(self.config, "reader@contoso.com", permission=Permission.READ)

        results = self.run_check()

        self.assertEqual(
            [(r.check, r.mailbox) for r in results],
            [("token", "-"), ("send", SCOPED), ("read", "reader@contoso.com"), ("read", DENY), ("send", DENY)],
        )

    def test_without_any_send_scope_there_is_no_deny_send_probe(self):
        self.config.mailbox_scopes.update(permission=Permission.READ)

        results = self.run_check()

        self.assertEqual([(r.check, r.mailbox) for r in results], [("token", "-"), ("read", SCOPED), ("read", DENY)])

    def test_granted_deny_access_fails_with_a_warning(self):
        self.probe.answer("GET", DENY, ALLOW_READ)
        self.probe.answer("POST", DENY, ALLOW_SEND)

        read, send = self.run_check()[-2:]

        self.assertFalse(read.passed)
        self.assertIn("ACCESS WAS GRANTED", read.note)
        self.assertFalse(send.passed)
        self.assertEqual(send.note, f"probe email sent to {SCOPED}")

    def test_a_missing_deny_mailbox_is_a_failure_with_a_note(self):
        self.probe.answer("GET", DENY, HttpResponse(404, {}, error_body("ErrorInvalidUser")))

        read = self.run_check(send=False)[-1]

        self.assertEqual((read.status, read.code, read.passed), (404, "ErrorInvalidUser", False))
        self.assertIn("mailbox not found", read.note)

    def test_a_refused_scoped_mailbox_fails(self):
        self.probe.answer("GET", SCOPED, DENIED)
        self.probe.answer("POST", SCOPED, DENIED)

        results = self.run_check()

        self.assertEqual([r.passed for r in results[1:3]], [False, False])
        self.assertEqual(results[1].note, "")

    def test_unreachable_graph_fails_the_probe(self):
        self.probe.answer("GET", SCOPED, transport.ConnectFailed())
        self.probe.answer("POST", SCOPED, transport.ResponseLost())

        read, send = self.run_check()[1:3]

        self.assertEqual((read.status, read.passed, read.note), (None, False, "Graph could not be reached."))
        self.assertEqual((send.status, send.passed, send.note), (None, False, "Graph outcome unknown."))

    def test_a_token_failure_stops_before_any_graph_request(self):
        self.probe.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')

        (result,) = self.run_check()

        self.assertIsInstance(result, ProbeResult)
        self.assertEqual((result.check, result.passed, result.status), ("token", False, None))
        self.assertTrue(result.note)
        self.assertEqual(self.probe.graph_calls(), [])
