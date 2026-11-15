import json

from apps.core.services.email import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph import transport
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.email_monitoring.telemetry.test_telemetry_graph_send import (
    Outcome,
    Status,
    TelemetryTestCase,
    stored_text,
)
from apps.core.tests.services.test_email_graph import ACCESS_TOKEN, KEY_LINE

from ..helpers import BODY_TEXT, REQUEST_ID, accepted, graph_error


class FailedSendTests(TelemetryTestCase):
    def test_a_throttle_records_429_and_the_retry_after_microsoft_asked_for(self):
        email, attempt = self.send_failing(
            graph_error(429, "ApplicationThrottled", headers={"retry-after": "17"}), TransientEmailDeliveryError
        )

        self.assertEqual((attempt.http_status, attempt.error_kind, attempt.retry_after_seconds), (429, "throttled", 17))
        self.assertEqual(
            (attempt.outcome, email.status, email.last_error_kind), (Outcome.TRANSIENT, Status.FAILED, "throttled")
        )

    def test_an_unauthorized_send_is_an_authentication_failure(self):
        email, attempt = self.send_failing(graph_error(401, "InvalidAuthenticationToken"), TransientEmailDeliveryError)

        self.assertEqual((attempt.http_status, attempt.error_kind, email.status), (401, "auth", Status.FAILED))

    def test_a_mailbox_restriction_is_classified_as_such(self):
        email, attempt = self.send_failing(graph_error(403, "ErrorAccessDenied"), PermanentEmailDeliveryError)

        self.assertEqual((attempt.http_status, attempt.error_kind), (403, "mailbox_restricted"))

    def test_another_forbidden_answer_is_access_denied(self):
        _email, attempt = self.send_failing(graph_error(403, "Forbidden"))

        self.assertEqual(attempt.error_kind, "forbidden")

    def test_not_found_is_classified(self):
        _email, attempt = self.send_failing(graph_error(404, "ResourceNotFound"))

        self.assertEqual((attempt.http_status, attempt.error_kind), (404, "not_found"))

    def test_a_server_error_may_have_sent_the_email_so_its_outcome_is_unknown(self):
        email, attempt = self.send_failing(graph_error(500, "InternalServerError"), UncertainEmailDeliveryError)

        self.assertEqual(
            (attempt.outcome, attempt.error_kind, email.status), (Outcome.UNCERTAIN, "server_error", Status.UNCERTAIN)
        )

    def test_service_unavailable_is_retryable_and_keeps_retry_after(self):
        email, attempt = self.send_failing(
            graph_error(503, "ServiceUnavailable", headers={"retry-after": "30"}), TransientEmailDeliveryError
        )

        self.assertEqual(
            (attempt.error_kind, attempt.retry_after_seconds, email.status), ("server_busy", 30, Status.FAILED)
        )

    def test_a_full_sender_mailbox_is_a_mailbox_restriction(self):
        _email, attempt = self.send_failing(graph_error(507))

        self.assertEqual((attempt.http_status, attempt.error_kind), (507, "mailbox_restricted"))

    def test_a_refused_token_request_is_an_authentication_failure_at_the_token_step(self):
        token_answer = HttpResponse(
            401,
            {"x-ms-request-id": REQUEST_ID},
            json.dumps({"error": "invalid_client", "error_codes": [7000215], "error_description": BODY_TEXT}).encode(),
        )
        self.fake.script(token=token_answer, send=accepted())

        with self.assertRaises(PermanentEmailDeliveryError):
            self.send()

        email = self.only_email()
        attempt = email.attempts.get()
        self.assertEqual((attempt.operation, attempt.http_status, attempt.error_kind), ("token", 401, "auth"))
        self.assertEqual(attempt.error_code, "invalid_client AADSTS7000215")
        self.assertEqual((attempt.request_id, email.status), (REQUEST_ID, Status.FAILED))
        self.assertEqual(self.fake.send_requests, [])

    def test_a_connection_failure_is_an_api_failure_that_sent_nothing(self):
        email, attempt = self.send_failing(transport.ConnectFailed(), TransientEmailDeliveryError)

        self.assertEqual(
            (attempt.error_kind, attempt.http_status, email.status), ("connect_failed", None, Status.FAILED)
        )
        self.assertTrue(attempt.client_request_id)

    def test_a_timeout_after_the_request_began_leaves_the_outcome_unknown(self):
        lost = transport.ResponseLost()
        lost.__cause__ = TimeoutError("timed out")

        email, attempt = self.send_failing(lost, UncertainEmailDeliveryError)

        self.assertEqual(
            (attempt.outcome, attempt.error_kind, email.status), (Outcome.UNCERTAIN, "timeout", Status.UNCERTAIN)
        )

    def test_no_body_text_token_or_key_is_ever_stored(self):
        self.send_failing(graph_error(400, "ErrorInvalidRecipients", inner="ErrorInvalidRecipients"))

        stored = stored_text()
        for secret in (BODY_TEXT, ACCESS_TOKEN, KEY_LINE, "Bearer"):
            self.assertNotIn(secret, stored)
