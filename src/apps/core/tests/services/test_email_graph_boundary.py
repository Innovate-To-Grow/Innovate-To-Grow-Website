"""Graph provider boundary: ``before_provider_call`` ordering, composition errors and sendMail outcome classification.

The callback marks the moment a message is handed to Microsoft, so everything before it must be definitive
(token and composition failures never reach the callback) and everything after it is classified by whether bytes
may already have been sent.
"""

import contextlib
import http.client
import ssl
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
)
from apps.core.services.email import (
    EmailDeliveryError,
    GraphProvider,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph import provider as graph_provider
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.services.test_email_graph import (
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

OUTCOME_OF = {
    TransientEmailDeliveryError: PROVIDER_OUTCOME_TRANSIENT,
    PermanentEmailDeliveryError: PROVIDER_OUTCOME_PERMANENT,
    UncertainEmailDeliveryError: PROVIDER_OUTCOME_UNCERTAIN,
}


class GraphCallbackBoundaryTests(GraphFixtureMixin, SimpleTestCase):
    def test_callback_runs_after_the_token_and_before_the_post(self):
        calls = []
        self.fake.log = calls

        make_provider().send(simple_message(), before_provider_call=lambda: calls.append("callback"))

        self.assertEqual(calls, ["token", "callback", "sendMail"])

    def test_callback_still_runs_before_the_post_when_the_token_is_cached(self):
        provider = make_provider()
        provider.send(simple_message())
        calls = []
        self.fake.log = calls

        provider.send(simple_message(), before_provider_call=lambda: calls.append("callback"))

        self.assertEqual(calls, ["callback", "sendMail"])

    def test_callback_runs_exactly_once_whatever_the_post_outcome(self):
        outcomes = {
            "accepted": graph_response(202),
            "rejected": graph_response(403, body=error_body("ErrorSendAsDenied")),
            "gateway error": graph_response(502),
            "unreachable": ConnectFailed(),
            "response lost": ResponseLost(),
        }
        for label, outcome in outcomes.items():
            with self.subTest(label):
                self.script(send=outcome)
                callback = MagicMock()

                with patch.object(graph_provider, "logger"), contextlib.suppress(EmailDeliveryError):
                    make_provider().send(simple_message(), before_provider_call=callback)

                callback.assert_called_once_with()

    def test_callback_is_not_called_and_nothing_is_posted_when_the_token_request_fails(self):
        failures = {
            "identity platform unreachable": (ConnectFailed(), TransientEmailDeliveryError),
            "tls verification failed": (ConnectFailed(verification_failed=True), PermanentEmailDeliveryError),
            "no answer": (ResponseLost(), TransientEmailDeliveryError),
            "credentials rejected": (
                HttpResponse(400, {}, b'{"error": "invalid_client"}'),
                PermanentEmailDeliveryError,
            ),
            "throttled": (HttpResponse(429, {"retry-after": "5"}, b""), TransientEmailDeliveryError),
            "outage": (HttpResponse(503, {}, b""), TransientEmailDeliveryError),
            "unreadable answer": (HttpResponse(200, {}, b"<html>"), TransientEmailDeliveryError),
        }
        for label, (outcome, expected) in failures.items():
            with self.subTest(label):
                self.script(token=outcome)
                callback = MagicMock()

                with self.assertRaises(expected):
                    make_provider().send(simple_message(), before_provider_call=callback)

                callback.assert_not_called()
                self.assertEqual(self.fake.send_requests, [])

    def test_callback_errors_propagate_unclassified_and_skip_the_post(self):
        errors = [
            RuntimeError("claim lost"),
            OSError("callback failed"),
            TimeoutError("callback timed out"),
            ssl.SSLError("callback tls failure"),
            http.client.HTTPException("callback http failure"),
            # The provider's own transport signals must not be reinterpreted when the callback raises them.
            ConnectFailed(),
            ResponseLost(),
            TransientEmailDeliveryError("callback asked for a retry"),
        ]
        for error in errors:
            with self.subTest(type(error).__name__):
                self.script()

                with self.assertRaises(type(error)) as caught:
                    make_provider().send(simple_message(), before_provider_call=MagicMock(side_effect=error))

                self.assertIs(caught.exception, error)
                self.assertEqual(len(self.fake.token_requests), 1)
                self.assertEqual(self.fake.send_requests, [])


class GraphCompositionTests(GraphFixtureMixin, SimpleTestCase):
    def assert_nothing_happened(self, callback):
        """Composition problems are definitive: no token request, no HTTP call, no callback."""
        self.assertEqual(self.fake.requests, [])
        callback.assert_not_called()

    def test_bcc_recipients_are_rejected_before_any_network_activity(self):
        callback = MagicMock()

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "Bcc"):
            make_provider().send(simple_message(bcc=("hidden@example.com",)), before_provider_call=callback)

        self.assert_nothing_happened(callback)

    def test_delivery_errors_from_the_mime_builder_pass_through_unchanged(self):
        callback = MagicMock()

        with self.assertRaises(PermanentEmailDeliveryError) as caught:
            make_provider().send(simple_message(to=()), before_provider_call=callback)

        self.assertEqual(str(caught.exception), "Email has no recipients.")
        self.assertIsNone(caught.exception.__cause__)
        self.assert_nothing_happened(callback)

    def test_every_delivery_error_class_is_re_raised_as_the_same_object(self):
        for error in (
            PermanentEmailDeliveryError("permanent"),
            TransientEmailDeliveryError("transient"),
            UncertainEmailDeliveryError("uncertain"),
        ):
            with self.subTest(type(error).__name__):
                callback = MagicMock()

                with patch.object(graph_provider, "build_mime_message", side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        make_provider().send(simple_message(), before_provider_call=callback)

                self.assertIs(caught.exception, error)
                self.assert_nothing_happened(callback)

    def test_value_and_unicode_errors_become_one_generic_permanent_error(self):
        messages = {
            "linefeed in the subject": simple_message(subject="Hello\nBcc: evil@example.com"),
            "unencodable character in the body": simple_message(text_body="broken \ud800 surrogate"),
        }
        for label, message in messages.items():
            with self.subTest(label):
                callback = MagicMock()

                with self.assertRaises(PermanentEmailDeliveryError) as caught:
                    make_provider().send(message, before_provider_call=callback)

                self.assertEqual(str(caught.exception), "The email could not be composed for Microsoft Graph.")
                self.assertIsInstance(caught.exception.__cause__, ValueError)
                self.assert_nothing_happened(callback)

    def test_a_unicode_error_raised_by_the_builder_is_also_generic_and_permanent(self):
        original = UnicodeError("builder failed on secret-looking text")

        with patch.object(graph_provider, "build_mime_message", side_effect=original):
            with self.assertRaises(PermanentEmailDeliveryError) as caught:
                make_provider().send(simple_message())

        self.assertNotIn("secret-looking", str(caught.exception))
        self.assertIs(caught.exception.__cause__, original)
        self.assertEqual(self.fake.requests, [])


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


class GraphUnexpectedErrorTests(GraphFixtureMixin, SimpleTestCase):
    def test_an_unexpected_error_after_the_callback_is_uncertain_and_leaks_nothing(self):
        leaky = ValueError(f"Invalid header value 'Bearer {ACCESS_TOKEN}' for {KEY_LINE}")
        provider = make_provider()

        with (
            patch.object(GraphProvider, "_post", side_effect=leaky),
            self.assertLogs(PROVIDER_LOGGER, level="ERROR") as logs,
            self.assertRaises(UncertainEmailDeliveryError) as caught,
        ):
            provider.send(simple_message())

        error = caught.exception
        self.assertEqual(error.outcome, PROVIDER_OUTCOME_UNCERTAIN)
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)
        logged = "\n".join(logs.output)
        self.assertIn("ValueError", logged)
        for leaked in (ACCESS_TOKEN, KEY_LINE):
            self.assertNotIn(leaked, str(error))
            self.assertNotIn(leaked, logged)

    def test_the_callback_still_runs_before_the_safety_net_and_its_errors_still_propagate(self):
        callback_error = RuntimeError("claim lost")
        provider = make_provider()

        with self.assertRaises(RuntimeError) as caught:
            provider.send(simple_message(), before_provider_call=MagicMock(side_effect=callback_error))

        self.assertIs(caught.exception, callback_error)
        self.assertEqual(self.fake.send_requests, [])
