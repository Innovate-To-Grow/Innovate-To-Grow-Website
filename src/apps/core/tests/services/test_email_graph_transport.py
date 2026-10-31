"""The bounded HTTPS client for the fixed Microsoft endpoints (``graph.transport.post``)."""

import http.client
import socket
import ssl
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.services.email.graph.transport import (
    MAX_RESPONSE_BYTES,
    USER_AGENT,
    ConnectFailed,
    HttpResponse,
    ResponseLost,
    post,
)

CONNECTION = "apps.core.services.email.graph.transport.HTTPSConnection"


def make_connection(*, status=200, headers=(), body=b""):
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = status
    response.getheaders.return_value = list(headers)
    response.read.return_value = body
    return connection


def do_post():
    return post("graph.microsoft.com", "/v1.0/users/x/sendMail", b"payload", {"X-Test": "1"}, timeout=12)


class GraphTransportPostTests(SimpleTestCase):
    @patch(CONNECTION)
    def test_connects_over_verified_tls_then_posts_and_always_closes(self, connection_class):
        connection = make_connection(status=202, headers=[("Request-Id", "abc"), ("Retry-After", "5")], body=b"{}")
        connection_class.return_value = connection
        caller_headers = {"Authorization": "Bearer fake-token"}

        response = post("graph.microsoft.com", "/v1.0/users/x/sendMail", b"payload", caller_headers, timeout=12)

        self.assertEqual(response, HttpResponse(202, {"request-id": "abc", "retry-after": "5"}, b"{}"))
        args, kwargs = connection_class.call_args
        self.assertEqual(args, ("graph.microsoft.com",))
        self.assertEqual(kwargs["port"], 443)
        self.assertEqual(kwargs["timeout"], 12)
        context = kwargs["context"]
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual([call[0] for call in connection.method_calls], ["connect", "request", "getresponse", "close"])
        connection.request.assert_called_once_with(
            "POST",
            "/v1.0/users/x/sendMail",
            body=b"payload",
            headers={"User-Agent": USER_AGENT, "Authorization": "Bearer fake-token"},
        )
        self.assertEqual(caller_headers, {"Authorization": "Bearer fake-token"})

    @patch(CONNECTION)
    def test_response_header_names_are_lower_cased(self, connection_class):
        connection_class.return_value = make_connection(headers=[("Retry-After", "5"), ("REQUEST-ID", "abc")])

        response = do_post()

        self.assertEqual(response.headers, {"retry-after": "5", "request-id": "abc"})

    @patch(CONNECTION)
    def test_redirects_are_returned_to_the_caller_not_followed(self, connection_class):
        connection = make_connection(status=302, headers=[("Location", "https://other.example/")])
        connection_class.return_value = connection

        response = do_post()

        self.assertEqual((response.status, response.headers), (302, {"location": "https://other.example/"}))
        connection_class.assert_called_once()
        connection.request.assert_called_once()

    @patch(CONNECTION)
    def test_reads_at_most_the_response_limit(self, connection_class):
        payload = b"x" * (MAX_RESPONSE_BYTES * 2)
        connection = make_connection()
        connection.getresponse.return_value.read.side_effect = lambda amount=None: payload[:amount]
        connection_class.return_value = connection

        response = do_post()

        self.assertEqual(len(response.body), MAX_RESPONSE_BYTES)
        self.assertTrue(response.truncated)
        # One byte past the limit tells a complete body from a cut-off one.
        connection.getresponse.return_value.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
        self.assertLessEqual(MAX_RESPONSE_BYTES, 1024 * 1024, "the limit must keep memory use small")

    @patch(CONNECTION)
    def test_connect_failures_are_reported_without_sending_anything(self, connection_class):
        cases = [
            ("certificate verification", ssl.SSLCertVerificationError(1, "certificate verify failed"), True),
            ("dns lookup", socket.gaierror(-2, "Name or service not known"), False),
            ("connection refused", ConnectionRefusedError(111, "Connection refused"), False),
            ("connect timeout", TimeoutError("timed out"), False),
            ("tls handshake", ssl.SSLError(1, "handshake failure"), False),
        ]
        for label, error, verification_failed in cases:
            with self.subTest(label):
                connection = make_connection()
                connection.connect.side_effect = error
                connection_class.return_value = connection

                with self.assertRaises(ConnectFailed) as caught:
                    do_post()

                self.assertIs(caught.exception.verification_failed, verification_failed)
                self.assertIs(caught.exception.__cause__, error)
                self.assertEqual(str(caught.exception), "connection failed")
                connection.request.assert_not_called()
                connection.getresponse.assert_not_called()
                connection.close.assert_called_once_with()

    @patch(CONNECTION)
    def test_failures_after_connecting_mean_the_response_was_lost(self, connection_class):
        errors = [
            OSError("broken pipe"),
            ConnectionResetError("reset by peer"),
            TimeoutError("read timed out"),
            ssl.SSLError("tls failure mid-stream"),
            http.client.RemoteDisconnected("closed without a response"),
            http.client.BadStatusLine(""),
            http.client.HTTPException("protocol violation"),
        ]
        for stage in ("request", "getresponse"):
            for error in errors:
                with self.subTest(stage=stage, error=type(error).__name__):
                    connection = make_connection()
                    getattr(connection, stage).side_effect = error
                    connection_class.return_value = connection

                    with self.assertRaises(ResponseLost) as caught:
                        do_post()

                    self.assertIs(caught.exception.__cause__, error)
                    connection.connect.assert_called_once_with()
                    connection.close.assert_called_once_with()

    @patch(CONNECTION)
    def test_body_read_failures_keep_the_status_and_headers(self, connection_class):
        cases = [
            ("incomplete read keeps the partial bytes", http.client.IncompleteRead(b"par", 10), b"par"),
            ("socket error", OSError("connection reset"), b""),
            ("protocol error", http.client.HTTPException("bad chunk"), b""),
        ]
        for label, error, expected_body in cases:
            with self.subTest(label):
                connection = make_connection(status=503, headers=[("Retry-After", "9")])
                connection.getresponse.return_value.read.side_effect = error
                connection_class.return_value = connection

                response = do_post()

                self.assertEqual(response, HttpResponse(503, {"retry-after": "9"}, expected_body))
                connection.close.assert_called_once_with()

    @patch(CONNECTION)
    def test_connection_is_closed_even_when_an_unexpected_error_escapes(self, connection_class):
        connection = make_connection()
        connection.request.side_effect = RuntimeError("unexpected")
        connection_class.return_value = connection

        with self.assertRaises(RuntimeError):
            do_post()

        connection.close.assert_called_once_with()
