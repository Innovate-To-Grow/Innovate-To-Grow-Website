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
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph import provider as graph_provider
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.services.graph.provider.test_email_graph import (
    GraphFixtureMixin,
    error_body,
    graph_response,
    make_provider,
    simple_message,
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
