class RecorderApp:
    def __init__(self):
        self.scope = None
        self.body = b""

    async def __call__(self, scope, receive, send):
        self.scope = dict(scope)
        if scope["type"] == "http":
            self.body = await read_test_body(receive)
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        elif scope["type"] == "websocket":
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.close", "code": 1000})


async def invoke_http(app, scope_overrides, *, body=b""):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    scope.update(scope_overrides)
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return messages


async def invoke_websocket(app, scope_overrides):
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "scheme": "ws",
        "path": "/",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "subprotocols": [],
    }
    scope.update(scope_overrides)
    messages = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return messages


async def read_test_body(receive) -> bytes:
    chunks = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)
