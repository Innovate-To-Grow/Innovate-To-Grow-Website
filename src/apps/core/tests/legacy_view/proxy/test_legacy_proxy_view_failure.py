from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.legacy_view.gateway.views import MAX_HTML_BYTES, legacy_proxy_view
from apps.core.tests.legacy_view.proxy.test_transport_and_views import (
    GATEWAY_SETTINGS,
    HEADER_NAME,
    SECRET,
    origin_handle,
)


@override_settings(**GATEWAY_SETTINGS)
class LegacyProxyViewFailureTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(pk="admin-user")
        patcher = patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer", return_value=self.user)
        self.require_viewer = patcher.start()
        self.addCleanup(patcher.stop)

    def request(self, method="get", path="/legacy-view/about"):
        return getattr(self.factory, method)(path, headers={HEADER_NAME: SECRET})

    def assert_generic_502(self, response):
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertEqual(response["Cache-Control"], "private, no-store, max-age=0")

    def proxy(self, handle, legacy_path="about"):
        with patch("apps.core.legacy_view.gateway.views.open_legacy_origin", return_value=handle):
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
            patch("apps.core.legacy_view.gateway.views.open_legacy_origin") as open_origin,
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
