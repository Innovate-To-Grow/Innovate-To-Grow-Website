import logging
from unittest.mock import patch

from apps.core.services.credential_store import CredentialStoreError, TransientCredentialStoreError
from apps.core.services.delivery_rates import Reason, SignalKind
from apps.core.services.email import PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.core.services.email.gmail.client import auth
from apps.core.services.email.gmail.client.errors import GmailTokenRefused
from apps.core.services.email.gmail.service_account import stored_key
from apps.core.services.email.sending.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.gmail_api_helpers import (
    CLIENT_ID,
    FakePost,
    token_error,
    token_response,
)
from apps.core.tests.services.gmail_api.client.test_gmail_auth import SENTINEL, GmailAuthTestCase


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
