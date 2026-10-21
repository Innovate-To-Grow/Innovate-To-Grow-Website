import threading

import requests
from i2g_admin.callback_server import CallbackServer


def test_callback_captures_query():
    server = CallbackServer()

    def fire():
        requests.get(server.redirect_uri + "?code=abc&state=xyz", timeout=5)

    worker = threading.Thread(target=fire)
    worker.start()
    try:
        query = server.wait_for_callback(timeout=5)
    finally:
        worker.join()
        server.close()
    assert query == {"code": "abc", "state": "xyz"}


def test_callback_timeout_returns_none():
    server = CallbackServer()
    try:
        assert server.wait_for_callback(timeout=0.2) is None
    finally:
        server.close()
