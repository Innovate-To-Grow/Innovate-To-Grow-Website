"""The Gmail API token exchange: the request, the per-process cache, the answer checks and Google's refusals."""

import logging
from unittest.mock import patch
from urllib.parse import parse_qs

import jwt
from django.test import TestCase

from apps.core.services.credential_store import CredentialStoreError, TransientCredentialStoreError
from apps.core.services.delivery_rates import Reason, SignalKind
from apps.core.services.email import PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.core.services.email.gmail import auth
from apps.core.services.email.gmail.access import credential_for, require_subject
from apps.core.services.email.gmail.errors import GmailTokenRefused
from apps.core.services.email.gmail.key import stored_key
from apps.core.services.email.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.gmail_api_helpers import (
    CLIENT_ID,
    SUBJECT,
    TOKEN,
    FakePost,
    reset_gmail_state,
    stored_config,
    token_error,
    token_response,
)

SENTINEL = "SENTINEL-c0ffee-must-never-be-echoed"


class GmailAuthTestCase(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.config = stored_config()
        self.credential = credential_for(self.config)
        self.subject = require_subject(self.config, SUBJECT)

    def token(self, *answers):
        self.post = FakePost(*answers).install(self)
        return auth.get_access_token(self.credential, self.subject)

    def read_spy(self):
        patcher = patch.object(stored_key, "read_key", wraps=stored_key.read_key)
        spy = patcher.start()
        self.addCleanup(patcher.stop)
        return spy


class TokenRequestTests(GmailAuthTestCase):
    def test_form_body_host_and_path_are_exact(self):
        self.assertEqual(self.token(token_response()), (TOKEN, True))
        (call,) = self.post.calls
        self.assertEqual((call["host"], call["path"]), ("oauth2.googleapis.com", "/token"))
        self.assertEqual(call["headers"]["Content-Type"], "application/x-www-form-urlencoded")
        form = parse_qs(call["body"].decode("ascii"), strict_parsing=True)
        self.assertEqual(set(form), {"grant_type", "assertion"})
        self.assertEqual(form["grant_type"], ["urn:ietf:params:oauth:grant-type:jwt-bearer"])
        claims = jwt.decode(form["assertion"][0], options={"verify_signature": False})
        self.assertEqual((claims["sub"], claims["scope"]), (SUBJECT, "https://www.googleapis.com/auth/gmail.send"))
        self.assertEqual(call["timeout"], 15)

    def test_a_cache_hit_performs_zero_store_reads(self):
        self.token(token_response())
        spy = self.read_spy()
        self.assertEqual(auth.get_access_token(self.credential, self.subject), (TOKEN, False))
        spy.assert_not_called()
        self.assertEqual(len(self.post.calls), 1)

    def test_a_new_key_version_misses_the_cache(self):
        self.token(token_response(), token_response())
        rotated = auth.GmailCredential(**{**self.credential.__dict__, "key_version_id": self.config.key_version_id})
        self.assertEqual(auth.get_access_token(rotated, self.subject)[1], False)
        moved = auth.GmailCredential(**{**self.credential.__dict__, "key_version_id": "0" * 36})
        with self.assertRaises(PermanentEmailDeliveryError):
            auth.get_access_token(moved, self.subject)  # a miss: it reads the store, which holds no such version

    def test_ttl_keeps_a_margin_and_long_lifetimes_are_capped(self):
        with patch.object(auth.time, "monotonic", return_value=1000.0):
            self.token(token_response(expires_in=999_999), token_response())
        with patch.object(auth.time, "monotonic", return_value=1000.0 + 3600 - 300 - 1):
            self.assertFalse(auth.get_access_token(self.credential, self.subject)[1])
        with patch.object(auth.time, "monotonic", return_value=1000.0 + 3600 - 300 + 1):
            self.assertTrue(auth.get_access_token(self.credential, self.subject)[1])

    def test_a_short_lifetime_is_cached_for_half_of_it(self):
        with patch.object(auth.time, "monotonic", return_value=0.0):
            self.token(token_response(expires_in=400), token_response())
        with patch.object(auth.time, "monotonic", return_value=199.0):
            self.assertFalse(auth.get_access_token(self.credential, self.subject)[1])
        with patch.object(auth.time, "monotonic", return_value=201.0):
            self.assertTrue(auth.get_access_token(self.credential, self.subject)[1])

    def test_scope_and_token_type_checks(self):
        broader = "https://www.googleapis.com/auth/gmail.send https://mail.google.com/"
        for answer, expected in (
            (token_response(scope=broader), PermanentEmailDeliveryError),
            (token_response(scope="https://mail.google.com/"), PermanentEmailDeliveryError),
            (token_response(token_type="mac"), PermanentEmailDeliveryError),
            (HttpResponse(status=200, headers={}, body=b"{not json"), TransientEmailDeliveryError),
            (HttpResponse(status=200, headers={}, body=b'{"access_token": "a b"}'), TransientEmailDeliveryError),
        ):
            with self.subTest(body=answer.body[:60]), self.assertRaises(expected):
                auth.clear_access_token_cache()
                self.token(answer)
        auth.clear_access_token_cache()
        self.assertEqual(self.token(token_response(scope=None)), (TOKEN, True))

    def test_a_subject_built_without_the_allow_list_check_is_refused_before_any_read(self):
        spy = self.read_spy()
        self.post = FakePost().install(self)
        for forged in (auth.AllowedSubject(SUBJECT), SUBJECT):
            with self.subTest(forged=forged), self.assertRaises(TypeError):
                auth.get_access_token(self.credential, forged)
        spy.assert_not_called()
        self.assertEqual(self.post.calls, [])


class TokenRefusalTests(GmailAuthTestCase):
    REFUSED = (
        ("unauthorized_client", "Unauthorized client or scope in request.", f"numeric client ID {CLIENT_ID}"),
        (
            "unauthorized_client",
            "Client is unauthorized to retrieve access tokens using this method, or client not authorized for any "
            "of the scopes requested.",
            "added the client by email instead of the numeric ID",
        ),
        ("access_denied", "Requested client not authorized.", "not authorized for client ID"),
        ("admin_policy_enforced", "", "administrator policy"),
        ("invalid_grant", "Invalid email or User ID", "does not exist"),
        ("invalid_grant", "Not a valid email.", "does not exist"),
        ("invalid_grant", "Invalid JWT Signature.", "deleted or belongs to another service account"),
        ("invalid_grant", "Invalid JWT: Token must be a short-lived token", "server clock"),
        ("invalid_grant", "something else", "(invalid_grant)"),
        ("disabled_client", "The OAuth client was disabled.", "disabled"),
        ("invalid_client", "", "does not know"),
        ("deleted_client", "", "deleted"),
        ("org_internal", "", "another organization"),
        ("invalid_scope", "", "not valid"),
    )

    def test_refusals_are_permanent_with_an_auth_breaker_and_the_cause(self):
        for code, description, cause in self.REFUSED:
            with self.subTest(code=code, description=description):
                with self.assertRaises(GmailTokenRefused) as caught:
                    self.token(token_error(code, description, status=401 if code == "invalid_client" else 400))
                self.assertEqual(caught.exception.code, code)
                self.assertIn(cause, str(caught.exception))
                self.assertTrue(str(caught.exception).startswith("Google rejected the Gmail API credentials"))
                self.assertEqual(caught.exception.rate_signal.kind, SignalKind.BLOCKED)
                self.assertEqual(caught.exception.rate_signal.reason, Reason.AUTH)

    def test_busy_answers_and_lost_connections_are_transient_pauses(self):
        cases = (
            token_error("temporarily_unavailable"),
            token_error("server_error", status=500),
            token_error("internal_failure"),
            token_error("rate_limit", status=429, headers={"retry-after": "7"}),
            token_error("", status=503),
            token_error("", status=408),
            ConnectFailed(),
            ResponseLost(),
        )
        for answer in cases:
            with self.subTest(answer=answer), self.assertRaises(TransientEmailDeliveryError) as caught:
                self.token(answer)
            self.assertEqual(caught.exception.rate_signal.kind, SignalKind.PAUSE)
        with self.assertRaises(TransientEmailDeliveryError) as caught:
            self.token(token_error("rate_limit", status=429, headers={"retry-after": "7"}))
        self.assertEqual(caught.exception.rate_signal.retry_after, 7)

    def test_a_tls_verification_failure_is_permanent(self):
        with self.assertRaises(PermanentEmailDeliveryError):
            self.token(ConnectFailed(verification_failed=True))

    def test_store_failures_are_classified(self):
        for error, expected, kind in (
            (TransientCredentialStoreError("busy", code="ThrottlingException"), TransientEmailDeliveryError, "pause"),
            (CredentialStoreError("gone", code="ResourceNotFoundException"), PermanentEmailDeliveryError, "blocked"),
            (stored_key.StoredKeyMismatch(), PermanentEmailDeliveryError, "blocked"),
        ):
            with self.subTest(error=error), patch.object(stored_key, "read_key", side_effect=error):
                with self.assertRaises(expected) as caught:
                    self.token(token_response())
                self.assertEqual(caught.exception.rate_signal.kind, kind)
                self.assertEqual(self.post.calls, [])

    def test_stored_facts_that_do_not_match_the_row_are_permanent(self):
        mismatched = auth.GmailCredential(**{**self.credential.__dict__, "key_id": "f" * 40})
        with self.assertRaises(PermanentEmailDeliveryError) as caught:
            self.post = FakePost(token_response()).install(self)
            auth.get_access_token(mismatched, self.subject)
        self.assertIn("does not match the installed key facts", str(caught.exception))
        self.assertEqual(self.post.calls, [])

    def test_nothing_google_sent_is_echoed_in_errors_or_logs(self):
        body = (f'{{"error": "invalid_grant", "error_description": "{SENTINEL}", "error_uri": "{SENTINEL}"}}').encode()
        for answer in (
            HttpResponse(status=400, headers={}, body=body),
            HttpResponse(status=500, headers={}, body=SENTINEL.encode()),
            HttpResponse(status=400, headers={}, body=f'{{"error": "{SENTINEL}"}}'.encode()),
            HttpResponse(status=200, headers={}, body=f'{{"access_token": "{SENTINEL} x"}}'.encode()),
        ):
            with self.subTest(status=answer.status), self.assertLogs("apps.core", level="DEBUG") as logs:
                logging.getLogger("apps.core").debug("start")
                with self.assertRaises(Exception) as caught:
                    self.token(answer)
            self.assertNotIn(SENTINEL, str(caught.exception))
            self.assertNotIn(SENTINEL, "\n".join(logs.output))
