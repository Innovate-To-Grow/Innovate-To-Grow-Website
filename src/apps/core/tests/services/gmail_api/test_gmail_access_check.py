"""The Gmail API access check: tokens per account, the site refusal, the breadth canary, the probe send, the
evidence it records, and ``verify_gmail_access``."""

from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs

import jwt
from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.core.models import GmailApiSubject
from apps.core.services.email.gmail.access_check import FAIL, PASS, SKIP, run_access_check
from apps.core.services.email.gmail.access_check.checks import BREADTH_SCOPES
from apps.core.tests.gmail_api_helpers import (
    SUBJECT,
    FakePost,
    reset_gmail_state,
    send_response,
    stored_config,
    token_error,
    token_response,
)

from ..delivery_rates.helpers import FakeClock

GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"


class ScopedTokenAnswers(FakePost):
    """Answers each token request by the scope its assertion asks for: gmail.send is issued, others refused (or,
    with ``broader``, issued too); sends get a 200 with the SENT label."""

    def __init__(self, *, broader=(), refuse_send_scope=False, send=None):
        super().__init__()
        self.broader = set(broader)
        self.refuse_send_scope = refuse_send_scope
        self.send = send or send_response()

    def __call__(self, host, path, body, headers, *, timeout):
        self.calls.append({"host": host, "path": path, "body": body, "headers": headers, "timeout": timeout})
        if path != "/token":
            return self.send
        scope = self.scope_of(body)
        if scope == GMAIL_SEND and not self.refuse_send_scope:
            return token_response()
        if scope in self.broader:
            return token_response(scope=scope)
        return token_error("unauthorized_client", "Client is unauthorized to retrieve access tokens.")

    @staticmethod
    def scope_of(body: bytes) -> str:
        assertion = parse_qs(body.decode())["assertion"][0]
        return jwt.decode(assertion, options={"verify_signature": False})["scope"]

    def token_scopes(self):
        return [self.scope_of(call["body"]) for call in self.calls if call["path"] == "/token"]


class AccessCheckTests(TestCase):
    def setUp(self):
        reset_gmail_state()
        FakeClock().install(self)
        self.config = stored_config(checked=False, verified=False)

    def run_check(self, answers=None, **options):
        self.post = (answers or ScopedTokenAnswers()).install(self)
        return run_access_check(self.config, **options)

    def outcomes(self, report, check):
        return [result.outcome for result in report.results if result.check == check]

    def test_a_clean_run_records_the_evidence(self):
        report = self.run_check()
        self.assertFalse(report.failed, [result.line() for result in report.results])
        self.assertTrue(report.recorded)
        self.config.refresh_from_db()
        self.assertTrue(self.config.access_check_current)
        self.assertTrue(self.config.subject_verified(SUBJECT))
        self.assertEqual(self.outcomes(report, "breadth"), [PASS] * len(BREADTH_SCOPES))
        self.assertEqual(self.outcomes(report, "send"), [PASS])
        self.assertEqual(self.post.token_scopes(), [GMAIL_SEND, *BREADTH_SCOPES])
        probe = self.post.calls[-1]
        self.assertEqual(probe["path"], "/upload/gmail/v1/users/me/messages/send?uploadType=media")
        self.assertIn(f"To: {SUBJECT}".encode(), probe["body"])

    def test_a_broader_delegation_fails_and_its_token_is_never_used(self):
        report = self.run_check(ScopedTokenAnswers(broader={"https://mail.google.com/"}))
        failures = [result for result in report.results if result.outcome == FAIL]
        self.assertEqual(len(failures), 1)
        self.assertIn("DELEGATION BROADER THAN gmail.send: https://mail.google.com/", failures[0].note)
        self.assertFalse(report.recorded)
        self.config.refresh_from_db()
        self.assertIsNone(self.config.access_checked_at)
        # The broad token went nowhere: the only send carries the gmail.send token.
        sends = [call for call in self.post.calls if call["path"] != "/token"]
        self.assertEqual(len(sends), 1)

    def test_the_site_refusal_makes_no_request_for_the_deny_subject(self):
        report = self.run_check(deny_subject="not-listed@g.ucmerced.edu")
        (refusal,) = [result for result in report.results if result.check == "refusal"]
        self.assertEqual((refusal.outcome, refusal.subject), (PASS, "not-listed@g.ucmerced.edu"))
        self.assertIn("no request sent to Google", refusal.note)
        subjects = {
            jwt.decode(parse_qs(c["body"].decode())["assertion"][0], options={"verify_signature": False})["sub"]
            for c in self.post.calls
            if c["path"] == "/token"
        }
        self.assertEqual(subjects, {SUBJECT})

    def test_a_listed_deny_subject_fails(self):
        report = self.run_check(deny_subject=SUBJECT)
        self.assertEqual(self.outcomes(report, "refusal"), [FAIL])
        self.assertFalse(report.recorded)

    def test_a_refused_token_fails_without_verifying_the_account(self):
        report = self.run_check(ScopedTokenAnswers(refuse_send_scope=True))
        self.assertEqual(self.outcomes(report, "token"), [FAIL])
        self.assertEqual(self.outcomes(report, "send"), [])
        self.assertIsNone(GmailApiSubject.objects.get(subject=SUBJECT).verified_at)

    def test_skipping_breadth_never_records_the_check_but_verifies_the_account(self):
        report = self.run_check(breadth=False)
        self.assertEqual(self.outcomes(report, "breadth"), [SKIP])
        self.assertFalse(report.recorded)
        self.assertIn("NOT A COMPLETE VALIDATION", report.conclusion())
        self.config.refresh_from_db()
        self.assertIsNone(self.config.access_checked_at)
        self.assertTrue(self.config.subject_verified(SUBJECT))

    def test_no_send_skips_the_probe_and_still_records(self):
        report = self.run_check(send=False)
        self.assertEqual(self.outcomes(report, "send"), [SKIP])
        self.assertTrue(report.recorded)
        self.assertNotIn(
            "/upload/gmail/v1/users/me/messages/send?uploadType=media", [c["path"] for c in self.post.calls]
        )

    def test_the_probe_expects_the_sent_label(self):
        report = self.run_check(ScopedTokenAnswers(send=send_response(labels=("INBOX",))))
        self.assertEqual(self.outcomes(report, "send"), [FAIL])
        self.assertTrue(report.recorded)  # checks 1-5 passed; the probe is reported, not evidence
        self.assertIn("send probe FAILED", report.conclusion())

    def test_evidence_is_not_written_for_a_key_rotated_during_the_run(self):
        answers = ScopedTokenAnswers()
        original = answers.__call__

        def rotate_then_answer(host, path, body, headers, *, timeout):
            type(self.config).objects.filter(pk=self.config.pk).update(key_version_id="9" * 36)
            return original(host, path, body, headers, timeout=timeout)

        with patch("apps.core.services.email.gmail.transport.post", rotate_then_answer):
            report = run_access_check(self.config)
        self.assertFalse(report.recorded)
        self.assertIsNone(GmailApiSubject.objects.get(subject=SUBJECT).verified_at)


class VerifyGmailAccessCommandTests(TestCase):
    def setUp(self):
        reset_gmail_state()
        FakeClock().install(self)
        self.config = stored_config(checked=False, verified=False)

    def call(self, *args, answers=None):
        (answers or ScopedTokenAnswers()).install(self)
        out = StringIO()
        call_command("verify_gmail_access", *args, stdout=out)
        return out.getvalue()

    def test_a_passing_run_prints_the_lines_and_exits_zero(self):
        output = self.call("--no-send")
        self.assertIn(f"PASS  token    {SUBJECT}", output)
        self.assertIn("Google-side per-user restriction: not available", output)
        self.config.refresh_from_db()
        self.assertTrue(self.config.access_check_current)

    def test_a_failing_run_exits_one(self):
        with self.assertRaises(CommandError):
            self.call(answers=ScopedTokenAnswers(broader={BREADTH_SCOPES[-1]}))

    def test_skip_breadth_records_nothing(self):
        output = self.call("--skip-breadth", "--no-send")
        self.assertIn("NOT A COMPLETE VALIDATION", output)
        self.config.refresh_from_db()
        self.assertIsNone(self.config.access_checked_at)

    def test_without_a_key_it_refuses_to_run(self):
        type(self.config).objects.update(key_secret_ref="", key_version_id="")
        with self.assertRaises(CommandError):
            self.call()
