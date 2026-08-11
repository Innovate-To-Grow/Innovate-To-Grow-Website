"""Security and transport tests for the bounded SNS HTTPS client."""

import ssl
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.utils.security import SecurityValidationError
from apps.mail.services.sns.http import SnsHttpError, fetch_sns_https


class FetchSnsHttpsTests(SimpleTestCase):
    @staticmethod
    def _connection(*, status=200, payload=b"ok"):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = payload
        return connection

    @patch("apps.mail.services.sns.http.HTTPSConnection")
    def test_fetches_validated_host_without_redirect_or_proxy_support(self, connection_class):
        connection = self._connection(payload=b"certificate")
        connection_class.return_value = connection

        result = fetch_sns_https(
            "https://sns.us-west-2.amazonaws.com/cert.pem?version=1",
            timeout=3,
            max_bytes=32,
        )

        self.assertEqual(result, b"certificate")
        connection_class.assert_called_once()
        args, kwargs = connection_class.call_args
        self.assertEqual(args, ("sns.us-west-2.amazonaws.com",))
        self.assertEqual(kwargs["port"], 443)
        self.assertEqual(kwargs["timeout"], 3)
        self.assertTrue(kwargs["context"].check_hostname)
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(kwargs["context"].minimum_version, ssl.TLSVersion.TLSv1_2)
        connection.request.assert_called_once_with(
            "GET",
            "/cert.pem?version=1",
            headers={"Accept": "*/*", "User-Agent": "i2g-sns-client/1"},
        )
        connection.getresponse.return_value.read.assert_called_once_with(33)
        connection.close.assert_called_once()

    @patch("apps.mail.services.sns.http.HTTPSConnection")
    def test_rejects_disallowed_url_before_opening_connection(self, connection_class):
        with self.assertRaises(SecurityValidationError):
            fetch_sns_https("file:///etc/passwd")

        connection_class.assert_not_called()

    @patch("apps.mail.services.sns.http.HTTPSConnection")
    def test_rejects_redirect_response(self, connection_class):
        connection_class.return_value = self._connection(status=302)

        with self.assertRaisesMessage(SnsHttpError, "HTTP 302"):
            fetch_sns_https("https://sns.us-west-2.amazonaws.com/redirect")

        connection_class.return_value.close.assert_called_once()

    @patch("apps.mail.services.sns.http.HTTPSConnection")
    def test_rejects_oversized_response(self, connection_class):
        connection_class.return_value = self._connection(payload=b"12345")

        with self.assertRaisesMessage(SnsHttpError, "4-byte limit"):
            fetch_sns_https("https://sns.us-west-2.amazonaws.com/cert.pem", max_bytes=4)

        connection_class.return_value.close.assert_called_once()
