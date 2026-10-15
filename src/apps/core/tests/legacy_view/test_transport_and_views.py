from __future__ import annotations

import http.client
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
from apps.core.legacy_view.views import MAX_HTML_BYTES, legacy_access_exchange_gateway, legacy_proxy_view
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

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_html_head_omits_metadata_for_the_unrewritten_origin_body(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": "100",
                "Content-Range": "bytes 0-99/100",
                "Content-Type": "text/html",
                "ETag": '"origin-body"',
            }
        )
        open_origin.return_value = handle

        response = legacy_proxy_view(self.request(method="head"), "about")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        for name in ("Accept-Ranges", "Content-Length", "Content-Range", "ETag"):
            self.assertNotIn(name, response)
        self.assertEqual(handle.response.read_calls, 0)

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_partial_html_is_rejected_instead_of_emitting_an_invalid_range(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(
            b"<html><body>Partial</body></html>",
            status=206,
            headers={"Content-Range": "bytes 0-9/100", "Content-Type": "text/html"},
        )
        open_origin.return_value = handle

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("Content-Range", response)
        self.assertTrue(handle.closed)

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

    @patch("apps.core.legacy_view.views.open_legacy_origin")
    @patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer")
    def test_malformed_utf8_path_returns_404_before_auth_or_origin(self, require_viewer, open_origin):
        for path in ("static/%FF", "static/%25FF", "static/%C3%28"):
            with self.subTest(path=path):
                response = legacy_proxy_view(self.request(path=f"/legacy-view/{path}"), path)
                self.assertEqual(response.status_code, 404)
        require_viewer.assert_not_called()
        open_origin.assert_not_called()

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


@override_settings(**GATEWAY_SETTINGS)
class LegacyTransportFailureTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_close_is_idempotent(self):
        handle = origin_handle()
        handle.connection = Mock()

        handle.close()
        handle.close()

        handle.connection.close.assert_called_once_with()
        self.assertTrue(handle.response.closed)

    def test_read_limited_rejects_body_over_limit(self):
        handle = origin_handle(b"x" * 11)

        with self.assertRaisesMessage(LegacyOriginUnavailable, "exceeded the size limit"):
            handle.read_limited(10)

    def test_read_limited_returns_body_within_limit(self):
        self.assertEqual(origin_handle(b"x" * 10).read_limited(10), b"x" * 10)

    def test_read_limited_wraps_socket_errors_generically(self):
        handle = origin_handle()
        handle.response.read = Mock(side_effect=http.client.IncompleteRead(b"partial"))

        with self.assertRaisesMessage(LegacyOriginUnavailable, "Legacy origin response failed."):
            handle.read_limited(10)

    def test_iter_chunks_wraps_errors_and_always_closes(self):
        handle = origin_handle()
        handle.response.read = Mock(side_effect=[b"first", ConnectionResetError("private detail")])

        chunks = handle.iter_chunks()
        self.assertEqual(next(chunks), b"first")
        with self.assertRaisesMessage(LegacyOriginUnavailable, "Legacy origin stream failed."):
            next(chunks)
        self.assertTrue(handle.closed)
        self.assertTrue(handle.connection.closed)

    def test_invalid_range_and_header_injection_are_not_forwarded(self):
        request = self.factory.get(
            "/legacy-view/static/file.pdf",
            headers={"Range": "bytes=0-1,2-3,4-5,6-7,8-9,10-11", "Accept-Language": "a" * 513},
        )

        headers = build_origin_headers(request)

        self.assertNotIn("Range", headers)
        self.assertNotIn("Accept-Language", headers)

    @patch("apps.core.legacy_view.transport.http.client.HTTPConnection")
    def test_connection_failure_closes_socket_and_raises_generic_error(self, connection_class):
        connection = connection_class.return_value
        connection.connect.side_effect = ConnectionRefusedError("172.31.69.63:8080 refused")

        with self.assertRaisesMessage(LegacyOriginUnavailable, "Legacy origin connection failed.") as raised:
            open_legacy_origin(self.factory.get("/about"), "/about", get_gateway_config())

        connection.close.assert_called_once_with()
        self.assertNotIn("172.31.69.63", str(raised.exception))


@override_settings(**GATEWAY_SETTINGS)
class LegacyProxyViewFailureTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(pk="admin-user")
        patcher = patch("apps.core.legacy_view.views.legacy_auth.require_legacy_viewer", return_value=self.user)
        self.require_viewer = patcher.start()
        self.addCleanup(patcher.stop)

    def request(self, method="get", path="/legacy-view/about"):
        return getattr(self.factory, method)(path, headers={HEADER_NAME: SECRET})

    def assert_generic_502(self, response):
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertEqual(response["Cache-Control"], "private, no-store, max-age=0")

    def proxy(self, handle, legacy_path="about"):
        with patch("apps.core.legacy_view.views.open_legacy_origin", return_value=handle):
            return legacy_proxy_view(self.request(path=f"/legacy-view/{legacy_path}"), legacy_path)

    def test_compressed_html_is_refused_with_generic_502(self):
        handle = origin_handle(b"\x1f\x8b", headers={"Content-Type": "text/html", "Content-Encoding": "gzip"})

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = self.proxy(handle)

        self.assert_generic_502(response)
        self.assertEqual(handle.response.read_calls, 0)
        self.assertTrue(handle.closed)

    def test_oversized_declared_html_is_refused_before_reading(self):
        handle = origin_handle(
            b"<html></html>",
            headers={"Content-Type": "text/html", "Content-Length": str(MAX_HTML_BYTES + 1)},
        )

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = self.proxy(handle)

        self.assert_generic_502(response)
        self.assertEqual(handle.response.read_calls, 0)
        self.assertTrue(handle.closed)

    def test_unknown_charset_falls_back_to_utf8(self):
        handle = origin_handle(
            "<html><body><p>Café</p></body></html>".encode(),
            headers={"Content-Type": 'text/html; charset="x-not-a-codec"'},
        )

        response = self.proxy(handle)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("Café", response.content.decode("utf-8"))

    def test_declared_legacy_charset_is_decoded_and_reencoded_as_utf8(self):
        handle = origin_handle(
            "<html><body><p>Café</p></body></html>".encode("latin-1"),
            headers={"Content-Type": "text/html; charset=ISO-8859-1"},
        )

        response = self.proxy(handle)

        self.assertIn("Café", response.content.decode("utf-8"))

    def test_empty_static_body_closes_origin_immediately(self):
        handle = origin_handle(b"", headers={"Content-Type": "text/css"})

        response = self.proxy(handle, "static/empty.css")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(handle.closed)
        self.assertEqual(b"".join(response.streaming_content), b"")

    def test_mid_stream_failure_truncates_and_logs_without_leaking(self):
        handle = origin_handle(headers={"Content-Type": "application/pdf"})
        handle.response.read = Mock(side_effect=[b"first-chunk", ConnectionResetError("172.31.69.63 reset")])

        response = self.proxy(handle, "static/file.pdf")
        with self.assertLogs("apps.core.legacy_view.views", level="WARNING") as captured:
            body = b"".join(response.streaming_content)

        self.assertEqual(body, b"first-chunk")
        self.assertIn("legacy_view_stream_failed path=/static/file.pdf", " ".join(captured.output))
        self.assertTrue(handle.closed)

    def test_malformed_location_on_streamed_asset_returns_generic_502(self):
        handle = origin_handle(
            b"bytes",
            headers={"Content-Type": "application/pdf", "Location": "http://[broken"},
        )

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = self.proxy(handle, "static/file.pdf")

        self.assert_generic_502(response)
        self.assertTrue(handle.closed)

    def test_misconfigured_gateway_returns_generic_502(self):
        with (
            override_settings(LEGACY_ORIGIN_URL="http://169.254.169.254"),
            patch("apps.core.legacy_view.views.open_legacy_origin") as open_origin,
            self.assertLogs("apps.core.legacy_view.views", level="ERROR"),
        ):
            response = legacy_proxy_view(self.request(), "about")

        self.assert_generic_502(response)
        self.assertNotIn(b"169.254", response.content)
        open_origin.assert_not_called()

    def test_ambiguous_path_returns_404_before_auth(self):
        with self.assertLogs("apps.core.legacy_view.views", level="INFO") as captured:
            response = legacy_proxy_view(self.request(path="/legacy-view/static/x"), "static/%2e%2e/admin")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"Not found.")
        self.assertIn("outcome=invalid_path", " ".join(captured.output))
        self.require_viewer.assert_not_called()

    def test_unexpected_auth_error_is_not_swallowed_as_403(self):
        self.require_viewer.side_effect = RuntimeError("database down")

        with self.assertRaises(RuntimeError):
            legacy_proxy_view(self.request(), "about")

    def test_not_modified_response_has_no_body(self):
        handle = origin_handle(b"ignored", status=304, headers={"ETag": '"v1"'})

        response = self.proxy(handle)

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["ETag"], '"v1"')
        self.assertEqual(handle.response.read_calls, 0)

    def test_header_injection_in_origin_headers_is_dropped(self):
        handle = origin_handle(b"data", headers={"Content-Type": "application/pdf"})
        handle.response.headers = {"Content-Type": "application/pdf", "Content-Disposition": "inline\r\nSet-Cookie: x"}

        response = self.proxy(handle, "static/file.pdf")

        self.assertNotIn("Content-Disposition", response)
        self.assertNotIn("Set-Cookie", response)
        response.close()
