from __future__ import annotations

from email.message import Message
from io import BytesIO
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.legacy_view.origin.config import get_gateway_config
from apps.core.legacy_view.origin.transport import (
    LegacyOriginHandle,
    build_origin_headers,
    build_origin_target,
    open_legacy_origin,
)

SECRET = "a-random-cloudfront-origin-value-with-32-characters"
HEADER_NAME = "X-I2G-Legacy-Origin-Secret"
VIEWER_URL = "https://d111111abcdef8.cloudfront.net"
GATEWAY_SETTINGS = {
    "LEGACY_VIEW_ENABLED": True,
    "LEGACY_ORIGIN_URL": "http://172.31.69.63:8080",
    "LEGACY_VIEWER_URL": VIEWER_URL,
    "LEGACY_ORIGIN_HEADER_NAME": HEADER_NAME,
    "LEGACY_ORIGIN_HEADER_VALUE": SECRET,
    "LEGACY_CONNECT_TIMEOUT_SECONDS": 2,
    "LEGACY_READ_TIMEOUT_SECONDS": 10,
}


class FakeOriginResponse:
    def __init__(self, body=b"", *, status=200, headers=None):
        self.status = status
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value
        self._body = BytesIO(body)
        self.read_calls = 0
        self.closed = False

    def read(self, amount=-1):
        self.read_calls += 1
        return self._body.read(amount)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def origin_handle(body=b"", *, status=200, headers=None):
    connection = FakeConnection()
    response = FakeOriginResponse(body, status=status, headers=headers)
    return LegacyOriginHandle(connection=connection, response=response)


@override_settings(**GATEWAY_SETTINGS)
class LegacyTransportTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_builds_encoded_target_with_only_allowed_query_fields(self):
        self.assertEqual(
            build_origin_target("/static/past projects/2025.pdf", "page=2&code=secret&q=capstone"),
            "/static/past%20projects/2025.pdf?page=2&q=capstone",
        )

    def test_forwards_range_validators_and_representation_headers_only(self):
        request = self.factory.get(
            "/legacy-view/static/file.pdf",
            headers={
                "Accept": "application/pdf",
                "Authorization": "Bearer secret",
                "Cookie": "sessionid=admin; csrftoken=secret",
                "If-None-Match": '"etag"',
                "Range": "bytes=10-99",
                "X-CSRFToken": "secret",
                "X-Forwarded-For": "203.0.113.20",
            },
        )

        headers = build_origin_headers(request)

        self.assertEqual(headers["Accept"], "application/pdf")
        self.assertEqual(headers["If-None-Match"], '"etag"')
        self.assertEqual(headers["Range"], "bytes=10-99")
        self.assertEqual(headers["Accept-Encoding"], "identity")
        for sensitive_name in ("Authorization", "Cookie", "X-CSRFToken", "X-Forwarded-For"):
            self.assertNotIn(sensitive_name, headers)

    @patch("apps.core.legacy_view.origin.transport.http.client.HTTPConnection")
    def test_connects_only_to_pinned_origin_and_applies_read_timeout(self, connection_class):
        upstream = FakeOriginResponse(headers={"Content-Type": "text/plain"})
        connection = connection_class.return_value
        connection.sock = Mock()
        connection.getresponse.return_value = upstream
        request = self.factory.get("/about?page=2&code=secret", headers={"Range": "bytes=0-9"})

        handle = open_legacy_origin(request, "/about", get_gateway_config())

        connection_class.assert_called_once_with("172.31.69.63", 8080, timeout=2.0)
        connection.connect.assert_called_once_with()
        connection.sock.settimeout.assert_called_once_with(10.0)
        connection.request.assert_called_once_with(
            "GET",
            "/about?page=2",
            body=None,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "I2G-Legacy-Read-Only-Gateway/1.0",
                "Range": "bytes=0-9",
            },
        )
        self.assertIs(handle.response, upstream)
