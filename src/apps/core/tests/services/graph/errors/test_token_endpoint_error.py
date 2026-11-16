from django.test import SimpleTestCase

from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
)
from apps.core.services.email import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph.errors import (
    graph_error_code,
    identity_error_code,
    send_mail_error,
    token_endpoint_error,
)
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph.errors.test_email_graph_errors import UNREADABLE_BODIES, as_body
from apps.core.tests.services.graph.provider.test_email_graph import RESPONSE_TEXT


class TokenEndpointErrorTests(SimpleTestCase):
    BODY = as_body(
        {
            "error": "invalid_client",
            "error_description": f"AADSTS7000215: Invalid client secret provided. {RESPONSE_TEXT}",
            "error_codes": [7000215],
            "trace_id": "trace-id-value",
            "correlation_id": "correlation-id-value",
        }
    )

    def assert_message_is_clean(self, error):
        for leaked in (RESPONSE_TEXT, "Invalid client secret", "trace-id-value", "correlation-id-value"):
            self.assertNotIn(leaked, str(error))

    def test_throttling_and_server_errors_are_transient_and_carry_retry_after(self):
        cases = [
            (408, {"retry-after": "5"}, 5.0),
            (429, {"retry-after": "30"}, 30.0),
            (429, {}, None),
            (500, {}, None),
            (502, {"retry-after": "7"}, 7.0),
            (503, {"retry-after": "99999"}, 3600.0),
            (599, {"retry-after": "not-a-number"}, None),
        ]
        for status, headers, retry_after in cases:
            with self.subTest(status=status, headers=headers):
                error = token_endpoint_error(HttpResponse(status, headers, self.BODY))

                self.assertIsInstance(error, TransientEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_TRANSIENT)
                self.assertEqual(error.retry_after, retry_after)
                self.assertIn("temporarily unavailable", str(error))
                self.assert_message_is_clean(error)

    def test_credential_rejections_are_permanent_and_name_the_error_codes(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                error = token_endpoint_error(HttpResponse(status, {}, self.BODY))

                self.assertIsInstance(error, PermanentEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_PERMANENT)
                self.assertIsNone(error.retry_after)
                self.assertEqual(str(error), "Microsoft rejected the Graph credentials (invalid_client AADSTS7000215).")
                self.assert_message_is_clean(error)

    def test_a_rejection_without_a_usable_code_names_nothing(self):
        for body in UNREADABLE_BODIES + [as_body({"error": "bad error!"})]:
            with self.subTest(body=body):
                error = token_endpoint_error(HttpResponse(400, {}, body))

                self.assertEqual(str(error), "Microsoft rejected the Graph credentials.")


class SendMailErrorTests(SimpleTestCase):
    BODY = as_body(
        {
            "error": {
                "code": "ErrorSendAsDenied",
                "message": f"Not allowed to send as this user. {RESPONSE_TEXT}",
                "innerError": {"request-id": "inner-request-id-value", "date": "2026-10-26T09:00:00"},
            }
        }
    )

    def error_for(self, status, headers=None, body=None):
        return send_mail_error(HttpResponse(status, headers or {}, self.BODY if body is None else body))

    def assert_message_is_clean(self, error):
        for leaked in (RESPONSE_TEXT, "Not allowed to send", "inner-request-id-value"):
            self.assertNotIn(leaked, str(error))

    def test_throttling_and_temporary_unavailability_are_transient_and_carry_retry_after(self):
        cases = [
            (408, {"retry-after": "5"}, 5.0),
            (429, {"retry-after": "30"}, 30.0),
            (429, {}, None),
            (503, {"retry-after": "120"}, 120.0),
            (503, {"retry-after": "99999"}, 3600.0),
            (503, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ]
        for status, headers, retry_after in cases:
            with self.subTest(status=status, headers=headers):
                error = self.error_for(status, headers)

                self.assertIsInstance(error, TransientEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_TRANSIENT)
                self.assertEqual(error.retry_after, retry_after)
                self.assertIn("temporarily rejected", str(error))
                self.assert_message_is_clean(error)

    def test_an_unauthorized_response_is_transient_because_the_token_will_be_refreshed(self):
        error = self.error_for(401)

        self.assertIsInstance(error, TransientEmailDeliveryError)
        self.assertIn("will be refreshed", str(error))
        self.assertIsNone(error.retry_after)
        self.assert_message_is_clean(error)

    def test_a_full_mailbox_is_permanent_with_a_specific_message(self):
        for body in (self.BODY, b""):
            with self.subTest(body=body):
                error = self.error_for(507, body=body)

                self.assertIsInstance(error, PermanentEmailDeliveryError)
                self.assertIn("mailbox is full", str(error))
                self.assert_message_is_clean(error)

    def test_client_errors_are_permanent_and_name_the_allow_listed_code(self):
        for status in (400, 403, 404, 413, 422):
            with self.subTest(status=status):
                error = self.error_for(status)

                self.assertIsInstance(error, PermanentEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_PERMANENT)
                self.assertEqual(str(error), "Microsoft Graph rejected the request (ErrorSendAsDenied).")
                self.assert_message_is_clean(error)

    def test_client_errors_without_a_usable_code_name_nothing(self):
        for body in UNREADABLE_BODIES:
            with self.subTest(body=body):
                error = self.error_for(400, body=body)

                self.assertEqual(str(error), "Microsoft Graph rejected the request.")

    def test_server_errors_and_unexpected_statuses_are_uncertain(self):
        for status in (500, 502, 504, 599, 200, 204, 302):
            with self.subTest(status=status):
                error = self.error_for(status)

                self.assertIsInstance(error, UncertainEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_UNCERTAIN)
                self.assertIsNone(error.retry_after)
                self.assertEqual(
                    str(error),
                    f"Microsoft Graph returned HTTP {status}; delivery could not be confirmed (ErrorSendAsDenied).",
                )
                self.assert_message_is_clean(error)

    def test_uncertain_errors_without_a_usable_code_name_nothing_after_the_status(self):
        error = self.error_for(502, body=b"<html>Bad Gateway</html>")

        self.assertEqual(str(error), "Microsoft Graph returned HTTP 502; delivery could not be confirmed.")


class HostileBodyTests(SimpleTestCase):
    NESTED = b"[" * 70_000

    def test_deeply_nested_bodies_are_treated_as_unreadable(self):
        self.assertEqual(graph_error_code(self.NESTED), "")
        self.assertEqual(identity_error_code(self.NESTED), "")

    def test_classification_survives_deeply_nested_bodies(self):
        for build in (send_mail_error, token_endpoint_error):
            with self.subTest(build.__name__):
                self.assertIsInstance(build(HttpResponse(400, {}, self.NESTED)), PermanentEmailDeliveryError)
