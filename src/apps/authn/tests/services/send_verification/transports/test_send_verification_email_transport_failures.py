import smtplib

from botocore.exceptions import ClientError, ReadTimeoutError
from django.test import override_settings

from apps.authn.tests.services.send_verification.transports.email_transport_case import (
    GRAPH_ERROR_BODY,
    _ProtectedEmailTransportCase,
)
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse, ResponseLost


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
)
class ProtectedEmailTransportTests(_ProtectedEmailTransportCase):
    def test_smtp_message_rejection_invalidates_otp_without_retry(self):
        self.exercise("smtp", send_error=smtplib.SMTPDataError(550, b"rejected"), expected_status=503)

    def test_smtp_connection_failure_is_definite_without_retry(self):
        self.exercise("smtp", connect_error=TimeoutError("unreachable"), expected_status=503)

    def test_smtp_accepted_message_survives_quit_failure(self):
        self.exercise("smtp", quit_error=smtplib.SMTPResponseException(500, b"QUIT failed"), expected_status=202)

    def test_ses_timeout_preserves_otp_with_sdk_retries_disabled(self):
        self.exercise("ses", send_error=ReadTimeoutError(endpoint_url="https://ses.example.com"), expected_status=409)

    def test_ses_rejection_invalidates_otp_without_retry(self):
        self.exercise(
            "ses",
            send_error=ClientError(
                {"Error": {"Code": "MessageRejected"}, "ResponseMetadata": {"HTTPStatusCode": 400}},
                "SendRawEmail",
            ),
            expected_status=503,
        )

    def test_graph_accepted_message_is_submitted_once_and_keeps_the_otp(self):
        self.exercise("graph", expected_status=202)

    def test_graph_throttling_is_definite_without_retry(self):
        throttled = HttpResponse(429, {"retry-after": "30"}, GRAPH_ERROR_BODY)

        self.exercise("graph", graph_response=throttled, expected_status=503)

    def test_graph_gateway_error_after_submission_preserves_otp_without_retry(self):
        self.exercise("graph", graph_response=HttpResponse(502, {}, GRAPH_ERROR_BODY), expected_status=409)

    def test_graph_permanent_rejection_invalidates_otp_without_retry(self):
        self.exercise("graph", graph_response=HttpResponse(403, {}, GRAPH_ERROR_BODY), expected_status=503)

    def test_graph_response_lost_after_submission_preserves_otp_without_retry(self):
        self.exercise("graph", send_error=ResponseLost(), expected_status=409)

    def test_graph_connection_failure_before_submission_is_definite_without_retry(self):
        self.exercise("graph", send_error=ConnectFailed(), expected_status=503)

    def test_graph_credential_rejection_is_definite_and_submits_nothing(self):
        rejected = HttpResponse(401, {}, b'{"error": "invalid_client", "error_codes": [7000215]}')

        self.exercise("graph", token_response=rejected, expected_status=503)
