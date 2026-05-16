"""ADK user-id rewrite helpers."""

import json
import re
from urllib.parse import parse_qsl, quote, urlencode

_USER_PATH_RE = re.compile(r"(/apps/[^/]+/users/)([^/]+)(/|$)")
_RUN_BODY_PATHS = frozenset({"/run", "/run_sse"})


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
        rewritten["query_string"] = _rewrite_query_user_id(rewritten.get("query_string", b""), adk_user_id)
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
