import asyncio
import json

from django.test import SimpleTestCase

from core.admin.system_intelligence.adk_web import AdminADKWebAuthMiddleware
from core.services.system_intelligence_adk.constants import APP_NAME

from .adk_web_helpers import RecorderApp, invoke_http, invoke_websocket


class AdminADKWebAuthMiddlewareTests(SimpleTestCase):
    def test_browser_shell_redirects_anonymous_user_to_admin_login(self):
        app = AdminADKWebAuthMiddleware(RecorderApp(), user_loader=_no_user)
        messages = asyncio.run(
            invoke_http(app, {"path": "/dev-ui/", "root_path": "/admin/core/system-intelligence/adk"})
        )

        self.assertEqual(messages[0]["status"], 302)
        self.assertEqual(messages[0]["headers"][0][0], b"location")
        self.assertIn(b"/admin/login/?next=/admin/core/system-intelligence/adk/dev-ui/", messages[0]["headers"][0][1])

    def test_api_rejects_unauthorized_user(self):
        app = AdminADKWebAuthMiddleware(RecorderApp(), user_loader=_no_user)
        messages = asyncio.run(invoke_http(app, {"path": "/list-apps"}))

        self.assertEqual(messages[0]["status"], 403)

    def test_staff_user_rewrites_path_user_id(self):
        recorder = RecorderApp()
        app = AdminADKWebAuthMiddleware(recorder, user_loader=_staff_user)
        messages = asyncio.run(invoke_http(app, {"path": f"/apps/{APP_NAME}/users/user/sessions", "method": "GET"}))

        self.assertEqual(messages[0]["status"], 204)
        self.assertEqual(recorder.scope["path"], f"/apps/{APP_NAME}/users/admin-42/sessions")

    def test_staff_user_rewrites_run_sse_body_user_id(self):
        recorder = RecorderApp()
        app = AdminADKWebAuthMiddleware(recorder, user_loader=_staff_user)
        body = json.dumps(
            {
                "appName": APP_NAME,
                "app_name": APP_NAME,
                "userId": "user",
                "user_id": "user",
                "sessionId": "session-1",
                "session_id": "session-1",
            }
        ).encode()
        messages = asyncio.run(invoke_http(app, {"path": "/run_sse", "method": "POST"}, body=body))

        self.assertEqual(messages[0]["status"], 204)
        rewritten_body = json.loads(recorder.body.decode())
        self.assertEqual(rewritten_body["user_id"], "admin-42")
        self.assertEqual(rewritten_body["userId"], "admin-42")
        self.assertIn((b"content-length", str(len(recorder.body)).encode()), recorder.scope["headers"])

    def test_staff_user_rewrites_run_live_query_user_id(self):
        recorder = RecorderApp()
        app = AdminADKWebAuthMiddleware(recorder, user_loader=_staff_user)
        asyncio.run(
            invoke_websocket(
                app,
                {
                    "path": "/run_live",
                    "query_string": f"app_name={APP_NAME}&user_id=user&session_id=session-1".encode(),
                },
            )
        )

        self.assertIn(b"user_id=admin-42", recorder.scope["query_string"])


async def _no_user(_headers):
    return None


async def _staff_user(_headers):
    return "42"
