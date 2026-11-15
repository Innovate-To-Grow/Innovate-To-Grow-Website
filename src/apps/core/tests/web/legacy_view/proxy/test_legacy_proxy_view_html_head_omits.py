from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings

from apps.core.legacy_view.access import LegacyViewerAccessDenied
from apps.core.legacy_view.gateway.views import legacy_proxy_view
from apps.core.legacy_view.origin.transport import (
    LegacyOriginUnavailable,
)
from apps.core.tests.web.legacy_view.proxy.test_legacy_proxy_view import _LegacyProxyViewCase
from apps.core.tests.web.legacy_view.proxy.test_transport_and_views import GATEWAY_SETTINGS, origin_handle


@override_settings(**GATEWAY_SETTINGS)
class LegacyProxyViewTest(_LegacyProxyViewCase):
    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin", side_effect=LegacyOriginUnavailable("timeout"))
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
    def test_origin_failure_returns_generic_502(self, require_viewer, open_origin):
        require_viewer.return_value = self.user

        with self.assertLogs("apps.core.legacy_view.views", level="ERROR"):
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.content, b"Legacy content is temporarily unavailable.")
        self.assertNotIn("172.31.69.63", response.content.decode())

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
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

    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
    def test_missing_cloudfront_header_returns_404_before_auth(self, require_viewer):
        response = legacy_proxy_view(self.request(trusted=False), "about")

        self.assertEqual(response.status_code, 404)
        require_viewer.assert_not_called()

    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
    def test_blocked_and_unknown_paths_never_reach_auth_or_origin(self, require_viewer):
        with (
            patch("apps.core.legacy_view.gateway.views.open_legacy_origin") as open_origin,
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

    @patch("apps.core.legacy_view.gateway.views.open_legacy_origin")
    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
    def test_malformed_utf8_path_returns_404_before_auth_or_origin(self, require_viewer, open_origin):
        for path in ("static/%FF", "static/%25FF", "static/%C3%28"):
            with self.subTest(path=path):
                response = legacy_proxy_view(self.request(path=f"/legacy-view/{path}"), path)
                self.assertEqual(response.status_code, 404)
        require_viewer.assert_not_called()
        open_origin.assert_not_called()

    @patch("apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer")
    def test_non_read_method_is_rejected_before_auth(self, require_viewer):
        response = legacy_proxy_view(self.request(method="post"), "about")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "GET, HEAD")
        require_viewer.assert_not_called()

    @patch(
        "apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer",
        side_effect=LegacyViewerAccessDenied("expired"),
    )
    def test_invalid_viewer_session_returns_403_and_clears_cookie(self, require_viewer):
        with self.assertLogs("apps.core.legacy_view.views", level="INFO") as captured_logs:
            response = legacy_proxy_view(self.request(), "about")

        self.assertEqual(response.status_code, 403)
        self.assertIn("i2g_legacy_viewer", response.cookies)
        self.assertEqual(response.cookies["i2g_legacy_viewer"]["max-age"], 0)
        self.assertIn("outcome=viewer_denied", " ".join(captured_logs.output))
