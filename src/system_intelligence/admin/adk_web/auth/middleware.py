"""ASGI middleware for staff-gating ADK web traffic."""

from .responses import _is_browser_shell_path, _send_plain_response, _send_redirect_to_admin_login
from .rewrite import _RUN_BODY_PATHS, _rewrite_json_body_user_id, _rewrite_scope_user_id
from .session import load_staff_user_id_from_headers


class AdminADKWebAuthMiddleware:
    """Require Django staff sessions and isolate ADK's user_id per admin user."""

    def __init__(self, app, *, user_loader=None):
        self.app = app
        self.user_loader = user_loader or load_staff_user_id_from_headers

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        user_pk = await self.user_loader(scope.get("headers", []))
        if user_pk is None:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            elif _is_browser_shell_path(scope.get("path", "")):
                await _send_redirect_to_admin_login(scope, send)
            else:
                await _send_plain_response(send, 403, b"Forbidden")
            return

        adk_user_id = f"admin-{user_pk}"
        rewritten_scope = _rewrite_scope_user_id(scope, adk_user_id)
        rewritten_receive = receive
        if rewritten_scope["type"] == "http" and rewritten_scope.get("path") in _RUN_BODY_PATHS:
            rewritten_receive = await _rewrite_json_body_user_id(rewritten_scope, receive, adk_user_id)
        await self.app(rewritten_scope, rewritten_receive, send)
