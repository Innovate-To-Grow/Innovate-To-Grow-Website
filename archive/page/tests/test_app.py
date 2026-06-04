"""Offline tests for the static server + Sheets proxy (no network, no real key)."""

import os
from pathlib import Path

import pytest

import app as app_module
from app import ALLOWED_SPREADSHEETS, app

A_SHEET = sorted(ALLOWED_SPREADSHEETS)[0]


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.test_client() as c:
        # Each test gets a cold cache so stubs aren't masked by cached bodies.
        app_module.cache.clear()
        yield c


def test_event_pages_are_served(client):
    resp = client.get("/2025-fall-event.html")
    assert resp.status_code == 200
    assert resp.content_type == "text/html; charset=utf-8"
    assert b"/api/sheets/" in resp.data


def test_served_page_includes_the_embed_helper(client):
    # Every served page gets the embed auto-resize/new-tab helper injected,
    # so the main site can iframe it cleanly.
    resp = client.get("/2025-fall-event.html")
    assert b'<script src="/static/js/i2g-embed.js"></script>' in resp.data
    # Injected right before the closing body tag, not appended after </html>.
    body_end = resp.data.lower().rfind(b"</body>")
    script_at = resp.data.find(b"/static/js/i2g-embed.js")
    assert -1 < script_at < body_end


def test_embed_helper_is_served_as_static(client):
    resp = client.get("/static/js/i2g-embed.js")
    assert resp.status_code == 200
    assert b"i2g-embed-resize" in resp.data


def test_embed_helper_injected_once_per_page(client):
    resp = client.get("/2025-fall-event.html")
    assert resp.data.count(b"/static/js/i2g-embed.js") == 1


def test_event_page_content_is_cached_in_process(client, monkeypatch):
    real_read_bytes = Path.read_bytes
    reads = 0

    def counted_read_bytes(path):
        nonlocal reads
        if path.name == "2025-fall-event.html":
            reads += 1
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    assert client.get("/2025-fall-event.html").status_code == 200
    assert client.get("/2025-fall-event.html").status_code == 200
    assert reads == 1


def test_event_page_cache_invalidates_when_file_changes(client, monkeypatch, tmp_path):
    page_path = tmp_path / "cached.html"
    page_path.write_text("<body>first</body>")
    monkeypatch.setattr(app_module, "PAGES_DIR", tmp_path)

    assert b"first" in client.get("/cached.html").data
    assert b"second" not in client.get("/cached.html").data

    page_path.write_text("<body>second</body>")
    stat = page_path.stat()
    os.utime(page_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))

    assert b"second" in client.get("/cached.html").data


def test_unknown_page_is_404(client):
    assert client.get("/nope.html").status_code == 404


def test_static_assets_are_served(client):
    assert client.get("/static/images/i2glogo.png").status_code == 200


def test_proxy_rejects_unknown_spreadsheet(client, monkeypatch):
    # Whitelist guard: must 404 BEFORE any upstream call is attempted.
    def boom(*a, **k):
        raise AssertionError("upstream must not be called")

    monkeypatch.setattr(app_module, "_fetch_values", boom)
    assert client.get("/api/sheets/not-a-real-sheet-id/values/A1:B2").status_code == 404


def test_proxy_rejects_bad_range(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("upstream must not be called")

    monkeypatch.setattr(app_module, "_fetch_values", boom)
    assert client.get(f"/api/sheets/{A_SHEET}/values/A1:B2;DROP").status_code == 404


def test_proxy_passes_through_values(client, monkeypatch):
    monkeypatch.setattr(
        app_module, "_fetch_values", lambda s, r: ({"range": r, "values": [["x"]]}, 200)
    )
    resp = client.get(f"/api/sheets/{A_SHEET}/values/I2G-Tracks")
    assert resp.status_code == 200
    assert resp.get_json() == {"range": "I2G-Tracks", "values": [["x"]]}


def test_proxy_maps_upstream_failure_to_502(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_fetch_values",
        lambda s, r: ({"error": "upstream request failed", "status": 403}, 502),
    )
    resp = client.get(f"/api/sheets/{A_SHEET}/values/I2G-Tracks")
    assert resp.status_code == 502
    # Sanitized error only — never the upstream URL (which would carry the key).
    assert b"AIzaSy" not in resp.data


def test_missing_key_is_a_server_error(client, monkeypatch):
    monkeypatch.delenv("SHEETS_API_KEY", raising=False)
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: pytest.fail("no upstream call"))
    resp = client.get(f"/api/sheets/{A_SHEET}/values/I2G-Tracks")
    assert resp.status_code == 500
