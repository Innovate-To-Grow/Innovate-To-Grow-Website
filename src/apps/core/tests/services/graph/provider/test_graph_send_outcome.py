from django.test import SimpleTestCase

from apps.core.services.email import (
    EmailDeliveryError,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph.transport import ConnectFailed, ResponseLost
from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    KEY_LINE,
    PROVIDER_LOGGER,
    REQUEST_ID,
    RESPONSE_TEXT,
    GraphFixtureMixin,
    error_body,
    graph_response,
    make_provider,
    simple_message,
    token_response,
)
from apps.core.tests.services.graph.provider.test_email_graph_boundary import OUTCOME_OF


class GraphSendOutcomeTests(GraphFixtureMixin, SimpleTestCase):
    RESPONSES = [
        # status, response headers, Graph error code, expected error, retry_after, text the message must contain
        (400, {}, "ErrorInvalidRecipients", PermanentEmailDeliveryError, None, "(ErrorInvalidRecipients)"),
        (403, {}, "ErrorSendAsDenied", PermanentEmailDeliveryError, None, "(ErrorSendAsDenied)"),
        (404, {}, "MailboxNotEnabledForRESTAPI", PermanentEmailDeliveryError, None, "(MailboxNotEnabledForRESTAPI)"),
        (413, {}, "", PermanentEmailDeliveryError, None, "rejected the request."),
        (422, {}, "", PermanentEmailDeliveryError, None, "rejected the request."),
        (507, {}, "ErrorQuotaExceeded", PermanentEmailDeliveryError, None, "mailbox is full"),
        (401, {}, "InvalidAuthenticationToken", TransientEmailDeliveryError, None, "will be refreshed"),
        (408, {"retry-after": "5"}, "", TransientEmailDeliveryError, 5.0, "temporarily rejected"),
        (429, {"retry-after": "30"}, "ApplicationThrottled", TransientEmailDeliveryError, 30.0, "temporarily rejected"),
        (429, {}, "", TransientEmailDeliveryError, None, "temporarily rejected"),
        (503, {"retry-after": "120"}, "", TransientEmailDeliveryError, 120.0, "temporarily rejected"),
        (500, {}, "InternalServerError", UncertainEmailDeliveryError, None, "HTTP 500"),
        (502, {}, "", UncertainEmailDeliveryError, None, "HTTP 502"),
        (504, {}, "", UncertainEmailDeliveryError, None, "HTTP 504"),
        (599, {}, "", UncertainEmailDeliveryError, None, "HTTP 599"),
        (200, {}, "", UncertainEmailDeliveryError, None, "HTTP 200"),
        (204, {}, "", UncertainEmailDeliveryError, None, "HTTP 204"),
        (302, {"location": "https://example.com/elsewhere"}, "", UncertainEmailDeliveryError, None, "HTTP 302"),
    ]

    def test_http_statuses_are_classified_by_retry_safety(self):
        for status, headers, code, expected, retry_after, fragment in self.RESPONSES:
            with self.subTest(status=status, code=code):
                body = error_body(code) if code else b""
                self.script(send=graph_response(status, body=body, headers=headers))

                with self.assertLogs(PROVIDER_LOGGER, level="WARNING"), self.assertRaises(expected) as caught:
                    make_provider().send(simple_message())

                error = caught.exception
                self.assertEqual(error.outcome, OUTCOME_OF[expected])
                self.assertEqual(error.retry_after, retry_after)
                self.assertIn(fragment, str(error))
                for leaked in (RESPONSE_TEXT, ACCESS_TOKEN, KEY_LINE):
                    self.assertNotIn(leaked, str(error))

    def test_transport_failures_while_posting_depend_on_whether_bytes_were_sent(self):
        cases = [
            ("connect failed", ConnectFailed(), TransientEmailDeliveryError, "could not be reached"),
            ("tls verification failed", ConnectFailed(verification_failed=True), PermanentEmailDeliveryError, "TLS"),
            ("response lost", ResponseLost(), UncertainEmailDeliveryError, "response was lost"),
        ]
        for label, failure, expected, fragment in cases:
            with self.subTest(label):
                self.script(send=failure)

                with self.assertRaises(expected) as caught:
                    make_provider().send(simple_message())

                self.assertEqual(caught.exception.outcome, OUTCOME_OF[expected])
                self.assertIn(fragment, str(caught.exception))
                self.assertIs(caught.exception.__cause__, failure)
                for leaked in (ACCESS_TOKEN, KEY_LINE):
                    self.assertNotIn(leaked, str(caught.exception))

    def assert_rejection_drops_the_token(self, status, expected_error):
        self.script(
            token=[token_response("token-one"), token_response("token-two")],
            send=[graph_response(status), graph_response(202)],
        )
        provider = make_provider()

        with self.assertLogs(PROVIDER_LOGGER, level="WARNING"), self.assertRaises(expected_error):
            provider.send(simple_message())
        provider.send(simple_message())

        self.assertEqual(len(self.fake.token_requests), 2)
        authorizations = [request.headers["Authorization"] for request in self.fake.send_requests]
        self.assertEqual(authorizations, ["Bearer token-one", "Bearer token-two"])

    def test_a_401_drops_the_cached_token_so_the_next_send_fetches_a_fresh_one(self):
        self.assert_rejection_drops_the_token(401, TransientEmailDeliveryError)

    def test_a_403_drops_the_cached_token_so_new_consent_applies_to_the_next_send(self):
        # A role granted after a token was issued only reaches newly issued tokens.
        self.assert_rejection_drops_the_token(403, PermanentEmailDeliveryError)

    def test_other_rejections_keep_the_cached_token(self):
        self.script(
            token=[token_response("token-one"), token_response("token-two")],
            send=[graph_response(404, body=error_body("MailboxNotEnabledForRESTAPI")), graph_response(202)],
        )
        provider = make_provider()

        with self.assertLogs(PROVIDER_LOGGER, level="WARNING"), self.assertRaises(PermanentEmailDeliveryError):
            provider.send(simple_message())
        provider.send(simple_message())

        self.assertEqual(len(self.fake.token_requests), 1)
        authorizations = [request.headers["Authorization"] for request in self.fake.send_requests]
        self.assertEqual(authorizations, ["Bearer token-one", "Bearer token-one"])


class GraphFailureLoggingTests(GraphFixtureMixin, SimpleTestCase):
    def failed_send_log(self, response):
        self.script(send=response)
        with self.assertLogs(PROVIDER_LOGGER, level="WARNING") as logs, self.assertRaises(EmailDeliveryError):
            make_provider().send(simple_message())
        self.assertEqual(len(logs.records), 1)
        self.assertIsNone(logs.records[0].exc_info)
        return logs.records[0].getMessage(), logs.output[0]

    def test_rejected_sends_log_the_status_error_code_and_request_id(self):
        headers = {"request-id": REQUEST_ID, "client-request-id": "00000000-0000-0000-0000-000000000000"}

        line, output = self.failed_send_log(graph_response(403, body=error_body("ErrorSendAsDenied"), headers=headers))

        self.assertIn("status=403", line)
        self.assertIn("code=ErrorSendAsDenied", line)
        self.assertIn(f"request_id={REQUEST_ID}", line)
        for leaked in (ACCESS_TOKEN, KEY_LINE, RESPONSE_TEXT):
            self.assertNotIn(leaked, output)

    def test_missing_code_and_request_id_are_logged_as_placeholders(self):
        line, _ = self.failed_send_log(graph_response(502))

        self.assertIn("status=502", line)
        self.assertIn("code=-", line)
        self.assertIn("request_id=-", line)

    def test_unsafe_code_and_request_id_values_are_not_logged(self):
        headers = {"request-id": "bad id\nforged log line"}
        body = b'{"error": {"code": "not a safe code\\nforged", "message": "' + RESPONSE_TEXT.encode() + b'"}}'

        line, output = self.failed_send_log(graph_response(400, body=body, headers=headers))

        self.assertIn("code=- request_id=-", line)
        self.assertNotIn("forged", output)
        self.assertNotIn(RESPONSE_TEXT, output)

    def test_accepted_sends_log_nothing(self):
        with self.assertNoLogs(PROVIDER_LOGGER, level="WARNING"):
            make_provider().send(simple_message())
