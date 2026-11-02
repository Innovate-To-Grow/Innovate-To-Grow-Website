"""Request-forgery regressions: nothing a viewer sends can steer the transport off the pinned origin."""

from __future__ import annotations

import dataclasses
import socket
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from apps.core.legacy_view.config import get_gateway_config
from apps.core.legacy_view.transport import LegacyOriginUnavailable, build_origin_target, open_legacy_origin

from .test_transport_and_views import GATEWAY_SETTINGS, HEADER_NAME, SECRET, FakeOriginResponse

# Paths a careless caller could hand the transport directly: unaudited or retired routes,
# non-canonical spellings, and targets that would leave origin-form.
HOSTILE_TRANSPORT_PATHS = [
    "",
    "about",
    "/admin",
    "/admin/user/edit/?id=1",
    "/confirm/one-time-code",
    "/event/1",
    "/not-audited",
    "/about?code=secret",
    "/about#fragment",
    "//evil.example/about",
    "http://169.254.169.254/latest/meta-data/",
    "@evil.example/about",
    "/static/../admin",
    "/static/%2e%2e/admin",
    "/static/%2Fadmin",
    "/static/a\\..\\admin",
    "/about\r\nHost: evil.example",
]

# Raw viewer URLs, resolved through the real URLconf: each must be refused by the view.
HOSTILE_VIEWER_URLS = {
    "/legacy-view/%2F%2Fevil.example/about": 404,
    "/legacy-view/http://169.254.169.254/latest/meta-data/": 404,
    "/legacy-view/@evil.example/about": 404,
    "/legacy-view/static/%252e%252e/admin": 404,
    "/legacy-view/static/..%5Cadmin": 404,
    "/legacy-view/admin%2Fuser": 410,
}


class _RecordingOrigin:
    """One-shot loopback HTTP origin that records the raw request head it receives."""

    def __init__(self):
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(5)
        self.port = self._listener.getsockname()[1]
        self.request_head = b""
        self._thread = threading.Thread(target=self._serve_once, daemon=True)
        self._thread.start()

    def _serve_once(self):
        try:
            connection, _address = self._listener.accept()
        except OSError:
            return
        with connection:
            connection.settimeout(5)
            while b"\r\n\r\n" not in self.request_head:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                self.request_head += chunk
            connection.sendall(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")

    def close(self):
        self._listener.close()
        self._thread.join(5)


@override_settings(**GATEWAY_SETTINGS)
class LegacyTransportForgeryTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_audited_routes_still_build_origin_form_targets(self):
        audited = {
            ("/", ""): "/",
            ("/", "page=2"): "/?page=2",
            ("/About", ""): "/About",
            ("/api/current-projects", "year=2025&semester=fall"): "/api/current-projects?year=2025&semester=fall",
            ("/past-projects/0f8fad5b-d9cb-469f-a165-70867728950e", ""): (
                "/past-projects/0f8fad5b-d9cb-469f-a165-70867728950e"
            ),
            ("/static/css/site.css", "_=1700000000"): "/static/css/site.css?_=1700000000",
        }
        for (path, query), expected in audited.items():
            with self.subTest(path=path, query=query):
                self.assertEqual(build_origin_target(path, query), expected)

    def test_target_builder_refuses_unaudited_and_non_origin_form_paths(self):
        for path in HOSTILE_TRANSPORT_PATHS:
            with self.subTest(path=path), self.assertRaises(LegacyOriginUnavailable):
                build_origin_target(path, "")

    def test_non_origin_form_target_is_refused_even_if_query_filtering_regresses(self):
        for query in ("q=1 HTTP/1.1\r\nHost: evil.example", "q=1#fragment", "q=@evil.example:80"):
            with (
                self.subTest(query=query),
                patch("apps.core.legacy_view.transport.filter_query_string", return_value=query),
                self.assertRaises(LegacyOriginUnavailable),
            ):
                build_origin_target("/about", "q=1")

    def test_reserved_characters_in_an_audited_path_stay_inside_the_path(self):
        self.assertEqual(
            build_origin_target("/static/x?admin=1#frag;@evil.example:80", ""),
            "/static/x%3Fadmin%3D1%23frag%3B%40evil.example%3A80",
        )

    def test_query_values_cannot_inject_path_host_or_header_lines(self):
        raw_query = "q=%0d%0aHost:%20evil.example&page=../../admin%23x&filter=http://169.254.169.254/&code=secret"

        self.assertEqual(
            build_origin_target("/about", raw_query),
            "/about?q=%0D%0AHost%3A+evil.example&page=..%2F..%2Fadmin%23x&filter=http%3A%2F%2F169.254.169.254%2F",
        )

    @patch("apps.core.legacy_view.transport.http.client.HTTPConnection")
    def test_hostile_paths_are_refused_before_any_connection_opens(self, connection_class):
        config = get_gateway_config()
        for path in HOSTILE_TRANSPORT_PATHS:
            with self.subTest(path=path), self.assertRaises(LegacyOriginUnavailable):
                open_legacy_origin(self.factory.get("/legacy-view/about"), path, config)
        connection_class.assert_not_called()

    @patch("apps.core.legacy_view.transport.http.client.HTTPConnection")
    def test_unsafe_methods_are_refused_before_any_connection_opens(self, connection_class):
        config = get_gateway_config()
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"):
            with self.subTest(method=method), self.assertRaises(LegacyOriginUnavailable):
                open_legacy_origin(self.factory.generic(method, "/legacy-view/about"), "/about", config)
        connection_class.assert_not_called()

    def test_wire_request_is_origin_form_with_the_configured_host_only(self):
        origin = _RecordingOrigin()
        self.addCleanup(origin.close)
        config = dataclasses.replace(get_gateway_config(), origin=urlsplit(f"http://127.0.0.1:{origin.port}"))
        request = self.factory.get(
            "/legacy-view/static/x%3Fadmin.pdf",
            QUERY_STRING="q=%0d%0aHost:%20evil.example&code=secret",
            headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example", "Cookie": "sessionid=admin"},
        )

        handle = open_legacy_origin(request, "/static/x?admin.pdf", config)
        handle.close()
        origin.close()

        self.assertEqual(handle.response.status, 204)
        request_line, *header_lines = origin.request_head.decode("latin-1").split("\r\n\r\n")[0].split("\r\n")
        self.assertEqual(request_line, "GET /static/x%3Fadmin.pdf?q=%0D%0AHost%3A+evil.example HTTP/1.1")
        host_lines = [line for line in header_lines if line.lower().startswith("host:")]
        self.assertEqual(host_lines, [f"Host: 127.0.0.1:{origin.port}"])
        forwarded = " ".join(header_lines).lower()
        self.assertNotIn("evil.example", forwarded)
        self.assertNotIn("cookie", forwarded)


@override_settings(**GATEWAY_SETTINGS)
class LegacyViewForgeryTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        patcher = patch(
            "apps.core.legacy_view.views.legacy_auth.require_legacy_viewer",
            return_value=SimpleNamespace(pk="viewer"),
        )
        self.require_viewer = patcher.start()
        self.addCleanup(patcher.stop)

    def dispatch(self, url, **extra):
        request = self.factory.get(url, headers={HEADER_NAME: SECRET}, **extra)
        match = resolve(request.path_info)
        return match.func(request, *match.args, **match.kwargs)

    @patch("apps.core.legacy_view.transport.http.client.HTTPConnection")
    def test_hostile_viewer_urls_never_reach_the_origin(self, connection_class):
        for url, expected_status in HOSTILE_VIEWER_URLS.items():
            with self.subTest(url=url):
                self.assertEqual(self.dispatch(url).status_code, expected_status)
        connection_class.assert_not_called()
        self.require_viewer.assert_not_called()

    @patch("apps.core.legacy_view.transport.http.client.HTTPConnection")
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
