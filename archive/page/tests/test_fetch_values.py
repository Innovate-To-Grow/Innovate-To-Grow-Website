import app as app_module
import pytest
import requests
from test_app import A_URL


def test_fetch_values_uses_trusted_url(monkeypatch):
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    captured = {}

    def fake_get(url, *a, **k):
        captured["url"] = url
        return _FakeResponse(200, {"values": []})

    monkeypatch.setattr(app_module.requests, "get", fake_get)
    app_module._fetch_values(A_URL)
    assert captured["url"] == A_URL


class _FakeResponse:
    def __init__(self, status_code=200, body=None, raises=False):
        self.status_code = status_code
        self._body = body
        self._raises = raises

    def json(self):
        if self._raises:
            raise ValueError("not json")
        return self._body


def test_fetch_values_passes_through_upstream_data(monkeypatch):
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: _FakeResponse(200, {"values": [["x"]]}))
    body, status = app_module._fetch_values(A_URL)
    assert status == 200
    assert body == {"values": [["x"]]}


def test_fetch_values_sanitizes_upstream_error(monkeypatch):
    # Upstream errors can echo the request URL (and with it the key) — only a
    # sanitized message may pass through.
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: _FakeResponse(403, {"error": "test-key leaked"}))
    body, status = app_module._fetch_values(A_URL)
    assert status == 502
    assert "test-key" not in str(body)


def test_fetch_values_handles_non_json_upstream(monkeypatch):
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: _FakeResponse(200, raises=True))
    body, status = app_module._fetch_values(A_URL)
    assert status == 502
    assert body == {"error": "upstream returned non-JSON"}


@pytest.mark.parametrize("error", [requests.Timeout("slow"), requests.ConnectionError("offline")])
def test_fetch_values_handles_request_exception(monkeypatch, error):
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: (_ for _ in ()).throw(error))
    body, status = app_module._fetch_values(A_URL)
    assert status == 502
    assert body == {"error": "upstream unavailable"}
