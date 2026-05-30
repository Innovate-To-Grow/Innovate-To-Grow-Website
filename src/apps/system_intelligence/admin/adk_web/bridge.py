"""Django HTTP bridge for the ADK web app."""

from asgiref.sync import async_to_sync
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .app import get_protected_system_intelligence_adk_asgi_application
from .constants import SYSTEM_INTELLIGENCE_ADK_PREFIX

_BRIDGE_APP = None
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@csrf_exempt
def adk_http_view(request, adk_path: str = ""):
    """Serve ADK HTTP routes when Django is running without the ASGI router."""
    messages = async_to_sync(_call_adk_app)(request)
    status, headers, body = _response_parts(messages)
    response = HttpResponse(body, status=status)
    for name, value in headers:
        if name.lower() not in _HOP_BY_HOP_HEADERS:
            response.headers[name] = value
    return response


async def _call_adk_app(request) -> list[dict]:
    messages = []
    body_sent = False

    async def receive():
        nonlocal body_sent
        if body_sent:
            return {"type": "http.disconnect"}
        body_sent = True
        return {"type": "http.request", "body": request.body, "more_body": False}

    async def send(message):
        messages.append(message)

    await _get_bridge_app()(_asgi_scope(request), receive, send)
    return messages


def _get_bridge_app():
    global _BRIDGE_APP
    if _BRIDGE_APP is None:
        _BRIDGE_APP = get_protected_system_intelligence_adk_asgi_application()
    return _BRIDGE_APP


def _asgi_scope(request) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": request.META.get("SERVER_PROTOCOL", "HTTP/1.1").split("/", 1)[-1],
        "method": request.method,
        "scheme": request.scheme,
        "path": request.path,
        "raw_path": request.path.encode("latin1"),
        "root_path": SYSTEM_INTELLIGENCE_ADK_PREFIX,
        "query_string": request.META.get("QUERY_STRING", "").encode("latin1"),
        "headers": _request_headers(request),
        "client": _client(request),
        "server": (request.get_host().split(":", 1)[0], _server_port(request)),
        "adk_original_path": request.path,
    }


def _request_headers(request) -> list[tuple[bytes, bytes]]:
    headers = []
    for key, value in request.META.items():
        if key.startswith("HTTP_"):
            name = key[5:].replace("_", "-").lower()
        elif key in {"CONTENT_LENGTH", "CONTENT_TYPE"}:
            name = key.replace("_", "-").lower()
        else:
            continue
        headers.append((name.encode("latin1"), str(value).encode("latin1")))
    return headers


def _client(request) -> tuple[str, int]:
    return (request.META.get("REMOTE_ADDR") or "127.0.0.1", 0)


def _server_port(request) -> int:
    try:
        return int(request.get_port())
    except ValueError:
        return 80


def _response_parts(messages: list[dict]) -> tuple[int, list[tuple[str, str]], bytes]:
    status = 500
    headers = []
    body_parts = []
    for message in messages:
        if message["type"] == "http.response.start":
            status = message["status"]
            headers = [(name.decode("latin1"), value.decode("latin1")) for name, value in message.get("headers", [])]
        elif message["type"] == "http.response.body":
            body_parts.append(message.get("body", b""))
    return status, headers, b"".join(body_parts)
