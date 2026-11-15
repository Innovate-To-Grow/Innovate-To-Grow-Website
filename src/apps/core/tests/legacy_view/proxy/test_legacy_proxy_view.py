from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.legacy_view.gateway.views import legacy_proxy_view
from apps.core.tests.legacy_view.proxy.test_transport_and_views import (
    GATEWAY_SETTINGS,
    HEADER_NAME,
    SECRET,
    VIEWER_URL,
    origin_handle,
)


class _LegacyProxyViewCase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(pk="admin-user")

    def request(self, method="get", path="/legacy-view/about", *, trusted=True, **extra):
        headers = dict(extra.pop("headers", {}))
        if trusted:
            headers[HEADER_NAME] = SECRET
        return getattr(self.factory, method)(path, headers=headers, **extra)


@override_settings(**GATEWAY_SETTINGS)
class LegacyProxyViewTest(_LegacyProxyViewCase):
    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
    def test_malformed_redirect_returns_generic_502_and_closes_origin(self, require_viewer, open_origin):
        require_viewer.return_value = self.user
        handle = origin_handle(status=302, headers={"Location": "http://[broken"})
        open_origin.return_value = handle

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertTrue(handle.closed)

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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
