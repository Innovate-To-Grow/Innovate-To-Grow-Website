from __future__ import annotations

from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.legacy_view.config import get_gateway_config
from apps.core.legacy_view.transport import (
    LegacyOriginHandle,
    LegacyOriginUnavailable,
    build_origin_headers,
    build_origin_target,
    open_legacy_origin,
)
from apps.core.legacy_view.views import legacy_access_exchange_gateway, legacy_proxy_view
from apps.core.services.legacy_access import LegacyViewerAccessDenied

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
            build_origin_target("/past projects/2025", "page=2&code=secret&q=capstone"),
            "/past%20projects/2025?page=2&q=capstone",
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

    @patch("apps.core.legacy_view.transport.http.client.HTTPConnection")
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


@override_settings(**GATEWAY_SETTINGS)
class LegacyProxyViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(pk="admin-user")

    def request(self, method="get", path="/legacy-view/about", *, trusted=True, **extra):
        headers = dict(extra.pop("headers", {}))
        if trusted:
            headers[HEADER_NAME] = SECRET
        return getattr(self.factory, method)(path, headers=headers, **extra)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_html_is_rewritten_and_sensitive_origin_headers_are_dropped(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(
            b"<html><body><form action='/update'><input></form><a href='/admin/'>Old admin</a></body></html>",
            headers={
                "Connection": "keep-alive",
                "Content-Length": "99",
                "Content-Type": "text/html; charset=utf-8",
                "Server": "nginx",
                "Set-Cookie": "legacy_admin=secret",
                "Transfer-Encoding": "chunked",
                "X-Powered-By": "Flask",
            },
        )
        open_origin.return_value = handle
        request = self.request()

        response = legacy_proxy_view(request, "about")
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("i2g-legacy-read-only-banner", body)
        self.assertIn("form-action 'none'", response["Content-Security-Policy"])
        self.assertIn('action="#"', body)
        self.assertIn('disabled=""', body)
        self.assertIn('data-legacy-write-disabled="true"', body)
        self.assertEqual(response["Content-Length"], str(len(response.content)))
        for name in ("Connection", "Server", "Set-Cookie", "Transfer-Encoding", "X-Powered-By"):
            self.assertNotIn(name, response)
        self.assertTrue(handle.connection.closed)
        self.assertTrue(handle.response.closed)
        self.assertTrue(request._i2g_legacy_origin_verified)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_streams_static_content_preserves_range_headers_and_closes_origin(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(
            b"image-bytes",
            status=206,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": "11",
                "Content-Range": "bytes 0-10/20",
                "Content-Type": "image/png",
                "Set-Cookie": "do-not-forward=1",
            },
        )
        open_origin.return_value = handle

        response = legacy_proxy_view(self.request(path="/legacy-view/static/images/logo.png"), "static/images/logo.png")

        self.assertEqual(response.status_code, 206)
        self.assertTrue(response.streaming)
        self.assertEqual(b"".join(response.streaming_content), b"image-bytes")
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertEqual(response["Content-Range"], "bytes 0-10/20")
        self.assertNotIn("Set-Cookie", response)
        self.assertTrue(handle.connection.closed)
        self.assertTrue(handle.response.closed)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_closing_unconsumed_stream_still_closes_private_origin(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(b"large-asset", headers={"Content-Type": "application/pdf"})
        open_origin.return_value = handle
        response = legacy_proxy_view(self.request(path="/legacy-view/static/file.pdf"), "static/file.pdf")

        response.close()

        self.assertEqual(handle.response.read_calls, 1)
        self.assertTrue(handle.closed)
        self.assertTrue(handle.connection.closed)
        self.assertTrue(handle.response.closed)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_initial_static_read_failure_returns_generic_502(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(headers={"Content-Type": "application/pdf"})
        handle.response.read = Mock(side_effect=TimeoutError("private socket timed out"))
        open_origin.return_value = handle

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = legacy_proxy_view(self.request(path="/legacy-view/static/file.pdf"), "static/file.pdf")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertNotIn(b"socket", response.content)
        self.assertTrue(handle.closed)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_rewrites_internal_redirect_location(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(
            status=302,
            headers={"Content-Length": "10", "Location": "http://legacy.i2g.ucmerced.edu/update/token"},
        )
        open_origin.return_value = handle

        response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{VIEWER_URL}/update/token")
        self.assertNotIn("Content-Length", response)
        self.assertTrue(handle.connection.closed)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_malformed_redirect_returns_generic_502_and_closes_origin(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(status=302, headers={"Location": "http://[broken"})
        open_origin.return_value = handle

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertTrue(handle.closed)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_head_returns_headers_without_reading_origin_body(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(b"not-read", headers={"Content-Length": "8", "Content-Type": "text/plain"})
        open_origin.return_value = handle

        response = legacy_proxy_view(self.request(method="head"), "about")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["Content-Length"], "8")
        self.assertEqual(handle.response.read_calls, 0)
        self.assertTrue(handle.connection.closed)

    @patch("apps.core.legacy_view.views.open_legacy_origin", side_effect=LegacyOriginUnavailable("timeout"))
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_origin_failure_returns_generic_502(self, require_viewer, open_origin):
        require_viewer.return_value = self.user

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertNotIn("172.31.69.63", response.content.decode())

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_origin_5xx_body_is_closed_and_replaced_with_generic_502(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(
            b"Flask traceback containing a database password",
            status=503,
            headers={"Content-Type": "text/html"},
        )
        open_origin.return_value = handle

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertNotIn(b"traceback", response.content)
        self.assertTrue(handle.closed)
        self.assertTrue(handle.connection.closed)
        self.assertTrue(handle.response.closed)

    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_missing_cloudfront_header_returns_404_before_auth(self, require_viewer):
        response = legacy_proxy_view(self.request(trusted=False), "about")

        self.assertEqual(response.status_code, 404)
        require_viewer.assert_not_called()

    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_blocked_and_unknown_paths_never_reach_auth_or_origin(self, require_viewer):
        with (
            patch("apps.core.legacy_view.views.open_legacy_origin") as open_origin,
            self.assertLogs("apps.core.legacy_view.views", level="INFO") as captured_logs,
        ):
            blocked = legacy_proxy_view(self.request(path="/legacy-view/admin/secret-token"), "admin/secret-token")
            unknown = legacy_proxy_view(
                self.request(path="/legacy-view/unreviewed/secret-token"), "unreviewed/secret-token"
            )

        self.assertEqual(blocked.status_code, 410)
        self.assertEqual(unknown.status_code, 404)
        require_viewer.assert_not_called()
        open_origin.assert_not_called()
        rendered_logs = " ".join(captured_logs.output)
        self.assertIn("outcome=blocked_path", rendered_logs)
        self.assertIn("outcome=unknown_path", rendered_logs)
        self.assertNotIn("secret-token", rendered_logs)

    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_non_read_method_is_rejected_before_auth(self, require_viewer):
        response = legacy_proxy_view(self.request(method="post"), "about")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "GET, HEAD")
        require_viewer.assert_not_called()

    @patch(
        "apps.core.legacy_view.views.legacy_auth.require_legacy_viewer",
        side_effect=LegacyViewerAccessDenied("expired"),
    )
    def test_invalid_viewer_session_returns_403_and_clears_cookie(self, require_viewer):
        with self.assertLogs("apps.core.legacy_view.views", level="INFO") as captured_logs:
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 403)
        self.assertIn("i2g_legacy_viewer", response.cookies)
        self.assertEqual(response.cookies["i2g_legacy_viewer"]["max-age"], 0)
        self.assertIn("outcome=viewer_denied", " ".join(captured_logs.output))


@override_settings(**GATEWAY_SETTINGS)
class LegacyExchangeGatewayTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_outer_callback_is_csrf_exempt(self):
        self.assertTrue(legacy_access_exchange_gateway.csrf_exempt)

    @patch("apps.core.views.legacy_access.legacy_access_exchange_view")
    def test_trusted_post_marks_origin_verified_and_dispatches_exchange(self, exchange_view):
        exchange_view.return_value = HttpResponse(status=303, headers={"Location": "/"})
        request = self.factory.post(
            "/legacy-view/_i2g-auth/exchange",
            {"code": "one-time-code"},
            headers={HEADER_NAME: SECRET},
        )

        response = legacy_access_exchange_gateway(request)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(request._i2g_legacy_origin_verified)
        exchange_view.assert_called_once_with(request)

    @patch("apps.core.views.legacy_access.legacy_access_exchange_view")
    def test_missing_origin_header_never_dispatches_exchange(self, exchange_view):
        request = self.factory.post("/legacy-view/_i2g-auth/exchange", {"code": "one-time-code"})

        response = legacy_access_exchange_gateway(request)

        self.assertEqual(response.status_code, 404)
        exchange_view.assert_not_called()

    @patch("apps.core.views.legacy_access.legacy_access_exchange_view")
    def test_only_post_can_reach_exchange(self, exchange_view):
        request = self.factory.get("/legacy-view/_i2g-auth/exchange", headers={HEADER_NAME: SECRET})

        response = legacy_access_exchange_gateway(request)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "POST")
        exchange_view.assert_not_called()
