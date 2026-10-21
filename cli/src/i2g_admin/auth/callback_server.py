from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

_RESPONSE_BODY = b"<html><body>Login complete. You may close this window and return to the terminal.</body></html>"


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        self.server.callback_query = {key: values[0] for key, values in query.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_RESPONSE_BODY)

    def log_message(self, *args):  # pragma: no cover - silence default stderr logging
        pass


class CallbackServer:
    """A one-shot loopback HTTP server that captures a single OAuth callback."""

    def __init__(self):
        self._server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        self._server.callback_query = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/callback"

    def wait_for_callback(self, timeout=300):
        """Block until one callback request arrives (or timeout). Returns the query dict or None."""
        self._server.timeout = timeout
        self._server.handle_request()
        return self._server.callback_query

    def close(self) -> None:
        self._server.server_close()
