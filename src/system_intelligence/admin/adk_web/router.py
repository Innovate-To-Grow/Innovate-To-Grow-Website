from .constants import SYSTEM_INTELLIGENCE_ADK_PREFIX


class SystemIntelligenceADKRouter:
    """Route the ADK URL prefix to the official ADK FastAPI application."""

    def __init__(self, django_app, adk_app, *, prefix: str = SYSTEM_INTELLIGENCE_ADK_PREFIX):
        self.django_app = django_app
        self.adk_app = adk_app
        self.prefix = prefix.rstrip("/")
        self.prefix_bytes = self.prefix.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await _complete_lifespan(receive, send)
            return

        path = scope.get("path", "")
        if scope["type"] in {"http", "websocket"} and _path_has_prefix(path, self.prefix):
            adk_scope = dict(scope)
            adk_scope["root_path"] = scope.get("root_path") or ""
            adk_scope["path"] = _strip_path_prefix(path, self.prefix)
            if "raw_path" in scope:
                adk_scope["raw_path"] = _strip_raw_path_prefix(scope["raw_path"], self.prefix_bytes)
            adk_scope["adk_original_path"] = path
            await self.adk_app(adk_scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return

        await self.django_app(scope, receive, send)


def _path_has_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _strip_path_prefix(path: str, prefix: str) -> str:
    stripped = path.removeprefix(prefix)
    return stripped or "/"


def _strip_raw_path_prefix(raw_path: bytes, prefix: bytes) -> bytes:
    if raw_path == prefix:
        return b"/"
    if raw_path.startswith(prefix + b"/"):
        return raw_path[len(prefix) :]
    return raw_path


async def _complete_lifespan(receive, send) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return
