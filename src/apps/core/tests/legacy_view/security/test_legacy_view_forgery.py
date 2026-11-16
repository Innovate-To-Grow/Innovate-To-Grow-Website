from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from apps.core.tests.legacy_view.security.test_transport_security import HOSTILE_VIEWER_URLS

from ..proxy.test_transport_and_views import GATEWAY_SETTINGS, HEADER_NAME, SECRET, FakeOriginResponse


@override_settings(**GATEWAY_SETTINGS)
class LegacyViewForgeryTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        patcher = patch(
            "apps.core.legacy_view.gateway.views.legacy_auth.require_legacy_viewer",
            return_value=SimpleNamespace(pk="viewer"),
        )
        self.require_viewer = patcher.start()
        self.addCleanup(patcher.stop)

    def dispatch(self, url, **extra):
        request = self.factory.get(url, headers={HEADER_NAME: SECRET}, **extra)
        match = resolve(request.path_info)
        return match.func(request, *match.args, **match.kwargs)

    @patch("apps.core.legacy_view.origin.transport.http.client.HTTPConnection")
    def test_hostile_viewer_urls_never_reach_the_origin(self, connection_class):
        for url, expected_status in HOSTILE_VIEWER_URLS.items():
            with self.subTest(url=url):
                self.assertEqual(self.dispatch(url).status_code, expected_status)
        connection_class.assert_not_called()
        self.require_viewer.assert_not_called()

    @patch("apps.core.legacy_view.origin.transport.http.client.HTTPConnection")
    def test_audited_viewer_url_reaches_only_the_pinned_origin(self, connection_class):
        connection = connection_class.return_value
        connection.sock = Mock()
        connection.getresponse.return_value = FakeOriginResponse(headers={"Content-Type": "application/pdf"})

        response = self.dispatch(
            "/legacy-view/static/x%3Fadmin%23y.pdf",
            QUERY_STRING="q=%0d%0aHost:%20evil.example&code=secret",
        )

        self.assertEqual(response.status_code, 200)
        connection_class.assert_called_once_with("172.31.69.63", 8080, timeout=2.0)
        method, target = connection.request.call_args.args
        self.assertEqual((method, target), ("GET", "/static/x%3Fadmin%23y.pdf?q=%0D%0AHost%3A+evil.example"))
