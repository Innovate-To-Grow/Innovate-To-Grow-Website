import json

from apps.core.services.email import EmailDeliveryError, PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.services.graph.auth.test_email_graph_auth import TokenTestCase
from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    KEY_LINE,
    RESPONSE_TEXT,
    token_response,
)


class GraphTokenFailureTests(TokenTestCase):
    def assert_message_is_clean(self, error):
        for leaked in (RESPONSE_TEXT, KEY_LINE, ACCESS_TOKEN, "trace-id-value"):
            self.assertNotIn(leaked, str(error))

    def test_transport_failures_are_classified_before_any_mail_is_sent(self):
        cases = [
            ("unreachable", ConnectFailed(), TransientEmailDeliveryError, "could not be reached"),
            (
                "tls verification",
                ConnectFailed(verification_failed=True),
                PermanentEmailDeliveryError,
                "TLS verification",
            ),
            ("no answer", ResponseLost(), TransientEmailDeliveryError, "did not answer"),
        ]
        for label, failure, expected, fragment in cases:
            with self.subTest(label):
                self.script(token=failure)

                with self.assertRaises(expected) as caught:
                    self.get_token()

                self.assertIn(fragment, str(caught.exception))
                self.assertIs(caught.exception.__cause__, failure)

    def test_rejected_credentials_are_permanent_and_name_only_the_error_codes(self):
        body = json.dumps(
            {
                "error": "invalid_client",
                "error_description": f"AADSTS700027: Client assertion failed signature validation. {RESPONSE_TEXT}",
                "error_codes": [700027],
                "trace_id": "trace-id-value",
                "correlation_id": "correlation-id-value",
            }
        ).encode()
        for status in (400, 401, 403):
            with self.subTest(status=status):
                self.script(token=HttpResponse(status, {}, body))

                with self.assertRaises(PermanentEmailDeliveryError) as caught:
                    self.get_token()

                self.assertIn("invalid_client AADSTS700027", str(caught.exception))
                self.assert_message_is_clean(caught.exception)
                self.assertNotIn("signature validation", str(caught.exception))
                self.assertNotIn("correlation-id-value", str(caught.exception))

    def test_a_rejection_without_a_readable_body_carries_no_code(self):
        for body in (b"", b"not json", b"[]", b'{"error": {"nested": "object"}}'):
            with self.subTest(body=body):
                self.script(token=HttpResponse(401, {}, body))

                with self.assertRaises(PermanentEmailDeliveryError) as caught:
                    self.get_token()

                self.assertEqual(str(caught.exception), "Microsoft rejected the Graph credentials.")

    def test_throttling_and_outages_are_transient_and_carry_retry_after(self):
        cases = [
            (408, {"retry-after": "5"}, 5.0),
            (429, {"retry-after": "45"}, 45.0),
            (429, {}, None),
            (500, {}, None),
            (503, {"retry-after": "3600"}, 3600.0),
            (503, {"retry-after": "99999"}, 3600.0),
        ]
        for status, headers, retry_after in cases:
            with self.subTest(status=status, headers=headers):
                self.script(token=HttpResponse(status, headers, f'{{"error": "{RESPONSE_TEXT}"}}'.encode()))

                with self.assertRaises(TransientEmailDeliveryError) as caught:
                    self.get_token()

                self.assertEqual(caught.exception.retry_after, retry_after)
                self.assert_message_is_clean(caught.exception)

    def test_unreadable_success_bodies_are_transient(self):
        bodies = {
            "not json": b"<html>Bad gateway</html>",
            "empty": b"",
            "invalid utf-8": b"\xff\xfe\x00garbage",
            "json list": b"[]",
            "json null": b"null",
            "json string": b'"token"',
            "missing token": b'{"expires_in": 3599}',
            "empty token": b'{"access_token": "", "expires_in": 3599}',
            "null token": b'{"access_token": null, "expires_in": 3599}',
            "non-string token": b'{"access_token": 12345, "expires_in": 3599}',
            "non-numeric lifetime": b'{"access_token": "token-one", "expires_in": "soon"}',
            "null lifetime": b'{"access_token": "token-one", "expires_in": null}',
        }
        for label, body in bodies.items():
            with self.subTest(label):
                self.script(token=HttpResponse(200, {}, body))

                with self.assertRaisesMessage(TransientEmailDeliveryError, "unreadable"):
                    self.get_token()

    def test_only_a_200_answer_can_provide_a_token(self):
        usable_looking_body = token_response().body
        for status in (201, 202, 204, 302):
            with self.subTest(status=status):
                self.script(token=[HttpResponse(status, {}, usable_looking_body), token_response("token-one")])

                with self.assertRaises(EmailDeliveryError):
                    self.get_token()

                # Nothing from the refused answer was cached, so the next call asks again.
                self.assertEqual(self.get_token(), "token-one")
                self.assertEqual(len(self.fake.token_requests), 2)

    def test_failures_are_not_cached(self):
        self.script(token=[HttpResponse(503, {}, b""), token_response("token-one")])

        with self.assertRaises(TransientEmailDeliveryError):
            self.get_token()

        self.assertEqual(self.get_token(), "token-one")
        self.assertEqual(len(self.fake.token_requests), 2)
