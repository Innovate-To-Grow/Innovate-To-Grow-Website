"""Archived I2G event pages — Jinja-rendered event pages + Google Sheets proxy.

The event pages render tables from Google Sheets. The Sheets API key lives
ONLY here on the server (read from .env, gitignored): the browser calls the
same-origin `/api/sheets/...` proxy and never sees the key.

Pages live under templates/events/ and extend templates/base.html (shared
head, CSS/JS includes, page scaffold, and the iframe embed helper).

Run:
    python app.py                                   # waitress on :5001
    flask --app app run --debug --port 5001         # Flask dev server
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template
from flask_caching import Cache
from sheets_allowlist import ALLOWED_SHEET_RANGES as ALLOWED_SHEET_RANGES
from sheets_allowlist import ALLOWED_SPREADSHEETS as ALLOWED_SPREADSHEETS
from sheets_allowlist import READINESS_SHEET_ID as READINESS_SHEET_ID
from sheets_allowlist import READINESS_SHEET_URL, TRUSTED_SHEET_URLS

load_dotenv()

ROOT = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
app.config.update(CACHE_TYPE="SimpleCache", CACHE_DEFAULT_TIMEOUT=3600)
cache = Cache(app)


EVENT_TEMPLATES = {
    "2020-fall-post-event": "events/2020-fall-post-event.html",
    "2021-fall-event": "events/2021-fall-event.html",
    "2021-spring-event": "events/2021-spring-event.html",
    "2022-fall-event": "events/2022-fall-event.html",
    "2022-spring-event": "events/2022-spring-event.html",
    "2023-fall-event": "events/2023-fall-event.html",
    "2023-spring-event": "events/2023-spring-event.html",
    "2024-fall-event": "events/2024-fall-event.html",
    "2024-spring-event": "events/2024-spring-event.html",
    "2025-fall-event": "events/2025-fall-event.html",
    "2025-spring-event": "events/2025-spring-event.html",
}


def _fetch_values(
    upstream_url: str,
    *,
    timeout_seconds: float = 10,
) -> tuple[dict, int]:
    """Server-side Google Sheets call. Kept separate so tests can stub it."""
    key = os.getenv("SHEETS_API_KEY", "")
    if not key:
        return {"error": "SHEETS_API_KEY is not configured"}, 500
    try:
        resp = requests.get(
            upstream_url,
            params={"alt": "json", "key": key},
            timeout=timeout_seconds,
        )
    except requests.RequestException:
        return {"error": "upstream unavailable"}, 502
    try:
        body = resp.json()
    except ValueError:
        return {"error": "upstream returned non-JSON"}, 502
    # Never echo upstream error details verbatim — they can include the request
    # URL (and with it the key). Pass through data, sanitize errors.
    if resp.status_code != 200:
        return {"error": "upstream request failed", "status": resp.status_code}, 502
    return body, 200


@app.route("/healthz")
def healthz():
    """Liveness probe for the load balancer — no upstream calls, no key needed."""
    return jsonify({"status": "ok"}), 200


@app.route("/readyz")
def readyz():
    """Readiness validates config and one bounded allowlisted Sheets request."""
    if not os.getenv("SHEETS_API_KEY", "").strip():
        return jsonify({"status": "not_ready", "sheets_api_key": "missing"}), 503
    _body, upstream_status = _fetch_values(
        READINESS_SHEET_URL,
        timeout_seconds=3,
    )
    if upstream_status != 200:
        return (
            jsonify(
                {
                    "status": "not_ready",
                    "sheets_api_key": "configured",
                    "sheets_upstream": "unavailable",
                }
            ),
            503,
        )
    return (
        jsonify(
            {
                "status": "ok",
                "sheets_api_key": "configured",
                "sheets_upstream": "ok",
            }
        ),
        200,
    )


def _cache_successful(response) -> bool:
    """Cache Sheets data only; transient/configuration failures must be retried."""
    # Flask-Caching evaluates the view's raw return value before Flask converts
    # ``(response, status)`` into a final Response object.
    if isinstance(response, tuple):
        return len(response) < 2 or response[1] == 200
    return getattr(response, "status_code", 200) == 200


@app.route("/api/sheets/<sheet_id>/values/<path:cell_range>")
@cache.cached(response_filter=_cache_successful)
def sheets_proxy(sheet_id: str, cell_range: str):
    upstream_url = TRUSTED_SHEET_URLS.get((sheet_id, cell_range))
    if upstream_url is None:
        abort(404)
    body, status = _fetch_values(upstream_url)
    return jsonify(body), status


@app.route("/<page>.html")
def serve_page(page: str):
    template = EVENT_TEMPLATES.get(page)
    if template is None:
        abort(404)
    # Jinja caches the compiled template in-process (and auto-reloads it in
    # debug mode), so no extra response caching is needed for these static pages.
    return render_template(template)


if __name__ == "__main__":
    # Production entrypoint only. For local development use the Flask CLI:
    #   flask --app app run --debug --port 5001
    from waitress import serve

    # The container listener must accept traffic from the ECS task ENI.
    serve(app, host="0.0.0.0", port=5001, threads=8)  # nosec B104
