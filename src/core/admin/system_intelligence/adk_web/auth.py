import json
import re
from http import cookies
from importlib import import_module
from urllib.parse import parse_qsl, quote, urlencode

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.db import close_old_connections
from django.utils.crypto import constant_time_compare

_USER_PATH_RE = re.compile(r"(/apps/[^/]+/users/)([^/]+)(/|$)")
_RUN_BODY_PATHS = frozenset({"/run", "/run_sse"})


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


async def load_staff_user_id_from_headers(headers) -> str | None:
    return await sync_to_async(_load_staff_user_id_from_headers_sync, thread_sensitive=True)(headers)


def _load_staff_user_id_from_headers_sync(headers) -> str | None:
    close_old_connections()
    try:
        session_key = _session_key_from_headers(headers)
        if not session_key:
            return None

        engine = import_module(settings.SESSION_ENGINE)
        session = engine.SessionStore(session_key=session_key)
        user_id = session.get(SESSION_KEY)
        # Member primary keys are UUIDs, so no valid persisted user id is falsy.
        if not user_id:
            return None

        try:
            user = get_user_model()._default_manager.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None

        if not user.is_active or not user.is_staff:
            return None

        session_hash = session.get(HASH_SESSION_KEY)
        if session_hash and hasattr(user, "get_session_auth_hash"):
            if not constant_time_compare(session_hash, user.get_session_auth_hash()):
                return None

        return str(user.pk)
    finally:
        close_old_connections()


def _session_key_from_headers(headers) -> str | None:
    cookie_header = "; ".join(value.decode("latin1") for name, value in headers if name.lower() == b"cookie")
    if not cookie_header:
        return None
    parsed = cookies.SimpleCookie()
    try:
        parsed.load(cookie_header)
    except cookies.CookieError:
        return None
    morsel = parsed.get(settings.SESSION_COOKIE_NAME)
    return morsel.value if morsel else None


def _rewrite_scope_user_id(scope, adk_user_id: str):
    rewritten = dict(scope)
    path = rewritten.get("path", "")
    rewritten["path"] = _rewrite_user_path(path, adk_user_id)
    if "raw_path" in rewritten:
        rewritten["raw_path"] = _rewrite_user_path(
            rewritten["raw_path"].decode("latin1"),
            quote(adk_user_id, safe=""),
        ).encode("latin1")
    if rewritten.get("path") == "/run_live":
        rewritten["query_string"] = _rewrite_query_user_id(
            rewritten.get("query_string", b""),
            adk_user_id,
        )
    return rewritten


def _rewrite_user_path(path: str, adk_user_id: str) -> str:
    return _USER_PATH_RE.sub(lambda match: match.group(1) + adk_user_id + match.group(3), path)


def _rewrite_query_user_id(query_string: bytes, adk_user_id: str) -> bytes:
    params = parse_qsl(query_string.decode("latin1"), keep_blank_values=True)
    replaced = False
    rewritten = []
    for key, value in params:
        if key == "user_id":
            rewritten.append((key, adk_user_id))
            replaced = True
        else:
            rewritten.append((key, value))
    if not replaced:
        rewritten.append(("user_id", adk_user_id))
    return urlencode(rewritten).encode("latin1")


async def _rewrite_json_body_user_id(scope, receive, adk_user_id: str):
    body = await _read_body(receive)
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        new_body = body
    else:
        if isinstance(payload, dict):
            payload["user_id"] = adk_user_id
            payload["userId"] = adk_user_id
            new_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            scope["headers"] = _replace_content_length(scope.get("headers", []), len(new_body))
        else:
            new_body = body

    sent = False

    async def replay_receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": new_body, "more_body": False}
        return await receive()

    return replay_receive


async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replace_content_length(headers, length: int):
    filtered = [(name, value) for name, value in headers if name.lower() != b"content-length"]
    filtered.append((b"content-length", str(length).encode("ascii")))
    return filtered


async def _send_redirect_to_admin_login(scope, send) -> None:
    original_path = scope.get("adk_original_path") or ((scope.get("root_path") or "") + scope.get("path", ""))
    if scope.get("query_string"):
        original_path += "?" + scope["query_string"].decode("latin1")
    location = f"/admin/login/?next={quote(original_path, safe='/?:=&')}".encode("latin1")
    await send(
        {
            "type": "http.response.start",
            "status": 302,
            "headers": [(b"location", location), (b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


async def _send_plain_response(send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _is_browser_shell_path(path: str) -> bool:
    return path in {"", "/", "/dev-ui", "/dev-ui/"} or path.startswith("/dev-ui/")
