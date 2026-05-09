"""ASGI response helpers for ADK web auth."""

from urllib.parse import quote


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
