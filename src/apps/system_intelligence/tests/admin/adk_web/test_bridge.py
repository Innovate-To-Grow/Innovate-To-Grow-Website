from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.system_intelligence.admin.adk_web.bridge import adk_http_view

from .adk_web_helpers import read_test_body


class SystemIntelligenceADKHTTPBridgeTests(SimpleTestCase):
    def test_bridge_routes_admin_adk_path_to_asgi_app(self):
        app = _FakeADKApp(body=b"adk ok")
        request = RequestFactory().generic(
            "POST",
            "/admin/system-intelligence/adk/run_sse?trace=1",
            data=b'{"message":"hello"}',
            content_type="application/json",
            HTTP_COOKIE="sessionid=abc",
            REMOTE_ADDR="10.0.0.5",
        )

        with mock.patch("apps.system_intelligence.admin.adk_web.bridge._get_bridge_app", return_value=app):
            response = adk_http_view(request, "run_sse")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"adk ok")
        self.assertEqual(response["content-type"], "text/plain")
        self.assertEqual(app.scope["path"], "/admin/system-intelligence/adk/run_sse")
        self.assertEqual(app.scope["root_path"], "/admin/system-intelligence/adk")
        self.assertEqual(app.scope["query_string"], b"trace=1")
        self.assertEqual(app.scope["adk_original_path"], "/admin/system-intelligence/adk/run_sse")
        self.assertIn((b"cookie", b"sessionid=abc"), app.scope["headers"])
        self.assertEqual(app.body, b'{"message":"hello"}')

    def test_admin_adk_url_is_registered_before_admin_catch_all(self):
        app = _FakeADKApp(body=b"dev ui")

        with mock.patch("apps.system_intelligence.admin.adk_web.bridge._get_bridge_app", return_value=app):
            response = self.client.get("/admin/system-intelligence/adk/dev-ui/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"dev ui")
        self.assertEqual(app.scope["path"], "/admin/system-intelligence/adk/dev-ui/")


class _FakeADKApp:
    def __init__(self, *, body: bytes):
        self.body = b""
        self.response_body = body
        self.scope = None

    async def __call__(self, scope, receive, send):
        self.scope = dict(scope)
        self.body = await read_test_body(receive)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": self.response_body})
