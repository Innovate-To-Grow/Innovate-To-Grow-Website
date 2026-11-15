import app as app_module
import pytest
from app import (
    ALLOWED_SHEET_RANGES,
    ALLOWED_SPREADSHEETS,
    TRUSTED_SHEET_URLS,
)
from test_app import A_RANGE, A_SHEET, A_URL


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


def test_proxy_does_not_cache_transient_failure(client, monkeypatch):
    responses = iter(
        [
            ({"error": "upstream unavailable"}, 502),
            ({"values": [["recovered"]]}, 200),
        ]
    )
    calls = []

    def fetch(url):
        calls.append(url)
        return next(responses)

    monkeypatch.setattr(app_module, "_fetch_values", fetch)
    first = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")
    second = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")

    assert first.status_code == 502
    assert second.status_code == 200
    assert second.get_json() == {"values": [["recovered"]]}
    assert calls == [A_URL, A_URL]


def test_proxy_caches_successful_response(client, monkeypatch):
    calls = []

    def fetch(url):
        calls.append(url)
        return {"values": [["cached"]]}, 200

    monkeypatch.setattr(app_module, "_fetch_values", fetch)
    first = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")
    second = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")

    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json() == {"values": [["cached"]]}
    assert calls == [A_URL]


def test_proxy_cache_keeps_allowed_ranges_separate(client, monkeypatch):
    first_pair, second_pair = sorted(ALLOWED_SHEET_RANGES)[:2]
    first_url = TRUSTED_SHEET_URLS[first_pair]
    second_url = TRUSTED_SHEET_URLS[second_pair]
    calls = []

    def fetch(url):
        calls.append(url)
        return {"values": [[url]]}, 200

    monkeypatch.setattr(app_module, "_fetch_values", fetch)
    for sheet_id, cell_range in (first_pair, second_pair, first_pair, second_pair):
        response = client.get(f"/api/sheets/{sheet_id}/values/{cell_range}")
        assert response.status_code == 200
        assert response.get_json() == {"values": [[TRUSTED_SHEET_URLS[(sheet_id, cell_range)]]]}

    assert calls == [first_url, second_url]


def test_missing_key_is_a_server_error(client, monkeypatch):
    monkeypatch.delenv("SHEETS_API_KEY", raising=False)
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: pytest.fail("no upstream call"))
    resp = client.get(f"/api/sheets/{A_SHEET}/values/{A_RANGE}")
    assert resp.status_code == 500
