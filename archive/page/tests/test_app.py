"""Offline tests for the page server + Sheets proxy (no network, no real key)."""

import app as app_module
import pytest
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
    # Every page extends base.html, which loads the embed auto-resize/new-tab
    # helper right before </body> so the main site can iframe it cleanly.
    resp = client.get("/2025-fall-event.html")
    assert b'<script src="/static/js/i2g-embed.js"></script>' in resp.data
    body_end = resp.data.lower().rfind(b"</body>")
    script_at = resp.data.find(b"/static/js/i2g-embed.js")
    assert -1 < script_at < body_end


def test_embed_helper_is_served_as_static(client):
    resp = client.get("/static/js/i2g-embed.js")
    assert resp.status_code == 200
    assert b"i2g-embed-resize" in resp.data


def test_embed_helper_unsets_fixed_container_width(client):
    # When framed, the helper overrides Bootstrap's fixed `.container` width so
    # the embed fills the iframe instead of leaving wide left/right gaps.
    resp = client.get("/static/js/i2g-embed.js")
    assert b"width: 100% !important; max-width: 100% !important;" in resp.data
    assert b".container," in resp.data


def test_embed_helper_included_once_per_page(client):
    resp = client.get("/2025-fall-event.html")
    assert resp.data.count(b"/static/js/i2g-embed.js") == 1


def test_event_page_render_is_deterministic_and_template_cached(client):
    # The compiled templates live in Jinja's in-process cache; repeated
    # requests render byte-identical output without re-parsing the source.
    app.jinja_env.cache.clear()
    first = client.get("/2025-fall-event.html")
    assert first.status_code == 200
    assert len(app.jinja_env.cache) >= 2  # child template + base.html
    second = client.get("/2025-fall-event.html")
    assert first.data == second.data


def test_unknown_page_is_404(client):
    assert client.get("/nope.html").status_code == 404


def test_base_template_is_not_served(client):
    # base.html lives outside templates/events/, so the route can't reach it.
    assert client.get("/base.html").status_code == 404


def test_serve_page_rejects_traversal(client):
    # %5c -> "\" and dot segments hit the explicit guards in serve_page.
    assert client.get("/..%5capp.html").status_code == 404
    assert client.get("/..html").status_code == 404  # page == "."
    assert client.get("/...html").status_code == 404  # page == ".."
    assert client.get("/events%2f2025-fall-event.html").status_code == 404


def test_footer_loads_a_single_jquery(client):
    # The Drupal export used to load jQuery twice in the footer (3.6.1 + 3.3.1);
    # base.html keeps only 3.6.1. (Pages may still load their own copy in-body
    # for inline scripts that execute during parsing.)
    resp = client.get("/2025-fall-event.html")
    footer = resp.data[resp.data.rfind(b"siteimprove.js") :]
    assert footer.count(b"ajax.googleapis.com/ajax/libs/jquery/3.6.1/jquery.min.js") == 1
    assert b"code.jquery.com/jquery-3.3.1.js" not in footer


def test_healthz_is_ok_without_a_key(client, monkeypatch):
    # The LB liveness probe must never touch Google or need the key.
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: pytest.fail("no upstream call"))
    monkeypatch.delenv("SHEETS_API_KEY", raising=False)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


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
    monkeypatch.setattr(app_module, "_fetch_values", lambda s, r: ({"range": r, "values": [["x"]]}, 200))
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
    body, status = app_module._fetch_values(A_SHEET, "A1:B2")
    assert status == 200
    assert body == {"values": [["x"]]}


def test_fetch_values_sanitizes_upstream_error(monkeypatch):
    # Upstream errors can echo the request URL (and with it the key) — only a
    # sanitized message may pass through.
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: _FakeResponse(403, {"error": "test-key leaked"}))
    body, status = app_module._fetch_values(A_SHEET, "A1:B2")
    assert status == 502
    assert "test-key" not in str(body)


def test_fetch_values_handles_non_json_upstream(monkeypatch):
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: _FakeResponse(200, raises=True))
    body, status = app_module._fetch_values(A_SHEET, "A1:B2")
    assert status == 502
    assert body == {"error": "upstream returned non-JSON"}
