from __future__ import annotations

import http.client
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.legacy_view.gateway.views import legacy_access_exchange_gateway
from apps.core.legacy_view.origin.config import get_gateway_config
from apps.core.legacy_view.origin.transport import (
    LegacyOriginUnavailable,
    build_origin_headers,
    open_legacy_origin,
)
from apps.core.tests.legacy_view.proxy.test_transport_and_views import (
    GATEWAY_SETTINGS,
    HEADER_NAME,
    SECRET,
    origin_handle,
)


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

        with self.assertLogs("apps.core.legacy_view.views", level="INFO") as logs:
            response = legacy_access_exchange_gateway(request)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(request._i2g_legacy_origin_verified)
        exchange_view.assert_called_once_with(request)
        # The dispatched line names the method as a literal: nothing from the request reaches the log.
        self.assertTrue(any("status=303 method=POST outcome=dispatched" in line for line in logs.output), logs.output)

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

    @patch("apps.core.legacy_view.origin.transport.http.client.HTTPConnection")
    def test_connection_failure_closes_socket_and_raises_generic_error(self, connection_class):
        connection = connection_class.return_value
        connection.connect.side_effect = ConnectionRefusedError("172.31.69.63:8080 refused")

        with self.assertRaisesMessage(LegacyOriginUnavailable, "Legacy origin connection failed.") as raised:
            open_legacy_origin(self.factory.get("/about"), "/about", get_gateway_config())

        connection.close.assert_called_once_with()
        self.assertNotIn("172.31.69.63", str(raised.exception))
