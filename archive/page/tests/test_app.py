"""Offline tests for the page server + Sheets proxy (no network, no real key)."""

import app as app_module
import pytest
from app import ALLOWED_SHEET_RANGES, ALLOWED_SPREADSHEETS, TRUSTED_SHEET_URLS, app

A_SHEET, A_RANGE = sorted(ALLOWED_SHEET_RANGES)[0]
A_URL = TRUSTED_SHEET_URLS[(A_SHEET, A_RANGE)]


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
    # Real page content rendered through base.html (the proxy-usage invariant
    # lives in test_static_site.py, which also covers extracted JS assets).
    assert b"Innovate To Grow" in resp.data


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
    # Event pages are served only through the fixed EVENT_TEMPLATES allowlist.
    assert client.get("/..%5capp.html").status_code == 404
    assert client.get("/..html").status_code == 404  # page == "."
    assert client.get("/...html").status_code == 404  # page == ".."
    assert client.get("/events%2f2025-fall-event.html").status_code == 404


def test_serve_page_rejects_non_slug_names(client):
    # Anything outside the event template allowlist is rejected, so request input
    # can't reach a filesystem path or template name sink.
    assert client.get("/Base.html").status_code == 404  # uppercase
    assert client.get("/app_config.html").status_code == 404  # underscore
    assert client.get("/.env.html").status_code == 404  # leading dot
    assert client.get("/%2e%2e%2fbase.html").status_code == 404  # encoded "../"
    assert client.get("/page%00.html").status_code == 404  # NUL byte


def test_serve_page_uses_fixed_template_allowlist(monkeypatch):
    from werkzeug.exceptions import NotFound

    rendered = {}
    monkeypatch.setattr(app_module, "render_template", lambda template: rendered.setdefault("template", template))
    with app.test_request_context():
        with pytest.raises(NotFound):
            app_module.serve_page("../base")
        assert app_module.serve_page("2025-fall-event") == "events/2025-fall-event.html"
    assert rendered["template"] == "events/2025-fall-event.html"


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
    assert client.get(f"/api/sheets/not-a-real-sheet-id/values/{A_RANGE}").status_code == 404


def test_proxy_rejects_bad_range(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("upstream must not be called")

    monkeypatch.setattr(app_module, "_fetch_values", boom)
    assert client.get(f"/api/sheets/{A_SHEET}/values/A1:B2;DROP").status_code == 404


def test_proxy_rejects_unlisted_valid_range(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("upstream must not be called")

    monkeypatch.setattr(app_module, "_fetch_values", boom)
    assert client.get(f"/api/sheets/{A_SHEET}/values/Sheet1!A1:B2").status_code == 404


def test_proxy_passes_through_values(client, monkeypatch):
    monkeypatch.setattr(app_module, "_fetch_values", lambda url: ({"url": url, "values": [["x"]]}, 200))
    resp = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")
    assert resp.status_code == 200
    assert resp.get_json() == {"url": A_URL, "values": [["x"]]}


def test_proxy_uses_canonical_allowlist_sheet_id(client, monkeypatch):
    # SSRF break: the value handed to _fetch_values is a trusted URL from the
    # server-side allowlist, never a request-composed URL.
    seen = {}

    def capture(upstream_url):
        seen["upstream_url"] = upstream_url
        return ({"ok": True}, 200)

    monkeypatch.setattr(app_module, "_fetch_values", capture)
    resp = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")
    assert resp.status_code == 200
    assert A_SHEET in ALLOWED_SPREADSHEETS
    assert seen["upstream_url"] == A_URL


def test_proxy_passes_through_allowed_range_with_colon(client, monkeypatch):
    sheet_id, cell_range = next(pair for pair in ALLOWED_SHEET_RANGES if ":" in pair[1])
    trusted_url = TRUSTED_SHEET_URLS[(sheet_id, cell_range)]
    monkeypatch.setattr(app_module, "_fetch_values", lambda url: ({"url": url}, 200))
    resp = client.get(f"/api/sheets/{sheet_id}/values/{cell_range}")
    assert resp.status_code == 200
    assert resp.get_json() == {"url": trusted_url}


def test_trusted_sheet_urls_quote_ranges():
    assert TRUSTED_SHEET_URLS[("1188BQGCadaysxPN7VkVdcFeLhOi4zbwDVWdeMCcQQB4", "A1:Y76")].endswith("/values/A1%3AY76")


def test_fetch_values_uses_trusted_url(monkeypatch):
    monkeypatch.setenv("SHEETS_API_KEY", "test-key")
    captured = {}

    def fake_get(url, *a, **k):
        captured["url"] = url
        return _FakeResponse(200, {"values": []})

    monkeypatch.setattr(app_module.requests, "get", fake_get)
    app_module._fetch_values(A_URL)
    assert captured["url"] == A_URL


def test_proxy_maps_upstream_failure_to_502(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_fetch_values",
        lambda url: ({"error": "upstream request failed", "status": 403}, 502),
    )
    resp = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")
    assert resp.status_code == 502
    # Sanitized error only — never the upstream URL (which would carry the key).
    assert b"AIzaSy" not in resp.data


def test_missing_key_is_a_server_error(client, monkeypatch):
    monkeypatch.delenv("SHEETS_API_KEY", raising=False)
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: pytest.fail("no upstream call"))
    resp = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")
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
