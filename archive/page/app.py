"""Archived I2G event pages — static file server + Google Sheets proxy.

The event pages render tables from Google Sheets. The Sheets API key lives
ONLY here on the server (read from .env, gitignored): the browser calls the
same-origin `/api/sheets/...` proxy and never sees the key.

Run:
    python app.py            # waitress on :5001
    python app.py --debug    # Flask dev server on :5001
"""

import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, send_from_directory
from flask_caching import Cache

load_dotenv()

ROOT = Path(__file__).resolve().parent

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

UPSTREAM = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{cell_range}"


def _fetch_values(sheet_id: str, cell_range: str) -> tuple[dict, int]:
    """Server-side Google Sheets call. Kept separate so tests can stub it."""
    key = os.getenv("SHEETS_API_KEY", "")
    if not key:
        return {"error": "SHEETS_API_KEY is not configured"}, 500
    resp = requests.get(
        UPSTREAM.format(sheet_id=sheet_id, cell_range=cell_range),
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


@app.route("/api/sheets/<sheet_id>/values/<path:cell_range>")
@cache.cached()
def sheets_proxy(sheet_id: str, cell_range: str):
    if sheet_id not in ALLOWED_SPREADSHEETS or not _RANGE_RE.match(cell_range):
        abort(404)
    body, status = _fetch_values(sheet_id, cell_range)
    return jsonify(body), status


@app.route("/<page>.html")
@cache.cached()
def serve_page(page: str):
    # Only the flat event pages at the repo root, nothing else.
    if "/" in page or not (ROOT / f"{page}.html").is_file():
        abort(404)
    return send_from_directory(ROOT, f"{page}.html")


if __name__ == "__main__":
    import sys

    if "--debug" in sys.argv:
        app.run(debug=True, host="0.0.0.0", port=5001)  # noqa: S104 - local dev only
    else:
        from waitress import serve

        serve(app, host="0.0.0.0", port=5001, threads=8)
