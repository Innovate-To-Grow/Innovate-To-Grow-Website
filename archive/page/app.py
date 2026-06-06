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
import re
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template
from flask_caching import Cache

load_dotenv()

ROOT = Path(__file__).resolve().parent
EVENTS_DIR = ROOT / "templates" / "events"

app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
app.config.update(CACHE_TYPE="simple", CACHE_DEFAULT_TIMEOUT=3600)
cache = Cache(app)

# Only the spreadsheets the archived pages actually use — keeps the proxy from
# being an open relay that lets anyone spend this key's quota.
ALLOWED_SPREADSHEETS = frozenset(
    {
        "1-p5yXTpgRKfbxVBuvehR8PPoxKCMRrHC_yXMfNNYB0E",
        "10_l1AyeiwCN8GZl6CfL6CwOwVH6K66zmrZd1xxVx7qk",
        "1188BQGCadaysxPN7VkVdcFeLhOi4zbwDVWdeMCcQQB4",
        "13Yds-sPSPjLSWYyCyIaHauTZ3lchGiNH1n-II6tJOMM",
        "19VoMJrwiybqCNlepCa6QTBYIx5mqzZBVeOcPNxNvLnc",
        "1AoW60T0IHSkqO4dUzYV6ErWxMHKOhg73NpddUc2ZUxM",
        "1ByRYKwPkrD4edUVyd3hw3nTDY31ygyyx0QZOANF2vyc",
        "1dZADXdBWnRw-EO-2pL3DuuNfFODqIzUflQ6yjyH_pUo",
        "1fLRbUOkzH1YJhsuV49tiQf0ahXa2U3TrekE8FJgdzOM",
        "1L3fgZFAWnwXbRqn2Gt8Qf14-MCGxB46KZ3lfWe1a5ps",
        "1MfFpZ0mn90UkqEuegBWopPqucfkmzzUWNl0oR2eSWdo",
        "1nqwEiLllm2wsL0SUUSIdT8nqspEMLFP41wtC-akKASE",
        "1NvgPCISxxyoi_GjM77lb2RPhaAqtulA7YA0-1DnwMSk",
        "1NYKJkIAlAqMQyXLZroqEfm4T5jnafj7ksTl66j-H_Kg",
        "1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik",
        "1TJZfQFYf0iw1SBcqrdnS_efOsFzIppMg1aOajE-atc4",
        "1VF29jHnlXbl02BK6_GPv91hADGM_QsvvM_SgH2X8Ohs",
        "1WuiISEzbd0VCeB6F9cdR3dYFsZoFHwV6GWPH9iYYKQQ",
        "1XA1WXfZyZ1GzaEmmCY5RNuHM-q1WEuAQ89vSuepJtp8",
    }
)

# A1-notation ranges / sheet names as used by the pages (no spaces or quotes).
_RANGE_RE = re.compile(r"^[A-Za-z0-9:!_-]{1,100}$")

# Event page filenames are all lowercase "<year>-<season>-..." slugs. The
# whitelist is checked before any path is constructed so a request value can
# never reach the filesystem unless it is a plain slug.
_PAGE_RE = re.compile(r"^[a-z0-9-]+$")

UPSTREAM = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{cell_range}"


def _fetch_values(sheet_id: str, cell_range: str) -> tuple[dict, int]:
    """Server-side Google Sheets call. Kept separate so tests can stub it."""
    key = os.getenv("SHEETS_API_KEY", "")
    if not key:
        return {"error": "SHEETS_API_KEY is not configured"}, 500
    # cell_range is already constrained to [A-Za-z0-9:!_-] by _RANGE_RE; quoting
    # only ever encodes ":" and "!" and keeps the value from steering the URL.
    resp = requests.get(
        UPSTREAM.format(sheet_id=sheet_id, cell_range=urllib.parse.quote(cell_range, safe="")),
        params={"alt": "json", "key": key},
        timeout=10,
    )
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


@app.route("/api/sheets/<sheet_id>/values/<path:cell_range>")
@cache.cached()
def sheets_proxy(sheet_id: str, cell_range: str):
    # Break the taint honestly: the upstream sheet_id is the allowlist's own
    # canonical member, never the raw request value. Unknown ids 404.
    sheet_id = next((s for s in ALLOWED_SPREADSHEETS if s == sheet_id), None)
    if sheet_id is None or not _RANGE_RE.match(cell_range):
        abort(404)
    body, status = _fetch_values(sheet_id, cell_range)
    return jsonify(body), status


@app.route("/<page>.html")
def serve_page(page: str):
    # Only the event pages under templates/events/, nothing else — base.html
    # lives outside events/ and is therefore unreachable through this route.
    # The slug whitelist is checked BEFORE any path is built, so a request
    # value can never reach the filesystem unless it matches [a-z0-9-]+ (every
    # real page does). All real pages match; "." / ".." / any path separator
    # are rejected by the regex.
    if not _PAGE_RE.match(page):
        abort(404)
    # Defense in depth: resolve the path and require it to stay directly inside
    # EVENTS_DIR, so even a future regex slip can't escape the directory.
    page_path = (EVENTS_DIR / f"{page}.html").resolve()
    if page_path.parent != EVENTS_DIR.resolve() or not page_path.is_file():
        abort(404)
    # Jinja caches the compiled template in-process (and auto-reloads it in
    # debug mode), so no extra response caching is needed for these static pages.
    return render_template(f"events/{page}.html")


if __name__ == "__main__":
    # Production entrypoint only. For local development use the Flask CLI:
    #   flask --app app run --debug --port 5001
    from waitress import serve

    serve(app, host="0.0.0.0", port=5001, threads=8)  # noqa: S104 - bind all interfaces in container
