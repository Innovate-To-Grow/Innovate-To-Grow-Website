"""``graph.transport.get``: the bounded GET used by the mailbox reader and the access check."""

import http.client
import ssl
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.services.email.graph.transport import USER_AGENT, ConnectFailed, HttpResponse, ResponseLost, get
from apps.core.tests.services.test_email_graph_transport import CONNECTION, make_connection


def do_get(max_bytes=100):
    return get(
        "graph.microsoft.com",
        "/v1.0/users/x/mailFolders/inbox/messages?$top=1",
        {"Accept": "application/json"},
        timeout=7,
        max_bytes=max_bytes,
    )


class GraphTransportGetTests(SimpleTestCase):
    @patch(CONNECTION)
    def test_sends_a_bodyless_get_over_verified_tls_and_closes(self, connection_class):
        connection = make_connection(status=200, headers=[("Request-Id", "abc")], body=b'{"value": []}')
        connection_class.return_value = connection

        response = do_get()

        self.assertEqual(response, HttpResponse(200, {"request-id": "abc"}, b'{"value": []}', truncated=False))
        args, kwargs = connection_class.call_args
        self.assertEqual(args, ("graph.microsoft.com",))
        self.assertEqual((kwargs["port"], kwargs["timeout"]), (443, 7))
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(kwargs["context"].minimum_version, ssl.TLSVersion.TLSv1_2)
        connection.request.assert_called_once_with(
            "GET",
            "/v1.0/users/x/mailFolders/inbox/messages?$top=1",
            body=None,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        self.assertEqual([call[0] for call in connection.method_calls], ["connect", "request", "getresponse", "close"])

    @patch(CONNECTION)
    def test_reads_one_byte_past_the_limit_to_detect_truncation(self, connection_class):
        connection = make_connection(body=b"x" * 11)
        connection_class.return_value = connection

        response = do_get(max_bytes=10)

        connection.getresponse.return_value.read.assert_called_once_with(11)
        self.assertEqual(response.body, b"x" * 10)
        self.assertTrue(response.truncated)

    @patch(CONNECTION)
    def test_a_body_of_exactly_the_limit_is_not_truncated(self, connection_class):
        connection_class.return_value = make_connection(body=b"x" * 10)

        response = do_get(max_bytes=10)

        self.assertEqual(response.body, b"x" * 10)
        self.assertFalse(response.truncated)

    @patch(CONNECTION)
    def test_incomplete_read_keeps_the_partial_body(self, connection_class):
        connection = make_connection()
        connection.getresponse.return_value.read.side_effect = http.client.IncompleteRead(b"part")
        connection_class.return_value = connection

        response = do_get()

        self.assertEqual((response.body, response.truncated), (b"part", False))

    @patch(CONNECTION)
    def test_body_read_failure_yields_an_empty_body(self, connection_class):
        connection = make_connection(status=404)
        connection.getresponse.return_value.read.side_effect = TimeoutError()
        connection_class.return_value = connection

        self.assertEqual(do_get(), HttpResponse(404, {}, b""))

    @patch(CONNECTION)
    def test_connect_failures_are_classified(self, connection_class):
        for error, verification_failed in (
            (ssl.SSLCertVerificationError("bad cert"), True),
            (ConnectionRefusedError(), False),
        ):
            with self.subTest(type(error).__name__):
                connection = make_connection()
                connection.connect.side_effect = error
                connection_class.return_value = connection

                with self.assertRaises(ConnectFailed) as caught:
                    do_get()
                self.assertIs(caught.exception.verification_failed, verification_failed)
                connection.request.assert_not_called()
                connection.close.assert_called_once()

    @patch(CONNECTION)
    def test_a_lost_response_is_reported(self, connection_class):
        connection = make_connection()
        connection.getresponse.side_effect = http.client.RemoteDisconnected()
        connection_class.return_value = connection

        with self.assertRaises(ResponseLost):
            do_get()
        connection.close.assert_called_once()
