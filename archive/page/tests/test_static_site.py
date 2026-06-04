"""Invariants for the archived event pages.

The pages are flat HTML, but their Sheets data flows through the same-origin
``/api/sheets/`` proxy in app.py — the Google API key must never appear in (or
be reachable from) anything the browser receives.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "templates").glob("*.html"))

_ASSET_RE = re.compile(r"""(?:src|href)=["'](static/[^"'?#]+)["']""")
_KEY_RE = re.compile(r"AIzaSy[A-Za-z0-9_-]+")


def test_pages_were_discovered():
    # Guard against the glob silently matching nothing.
    assert len(PAGES) > 5


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_unrendered_jinja(page):
    text = page.read_text()
    assert "{{" not in text and "{%" not in text, f"{page.name} still contains Jinja"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_api_key_or_direct_google_calls(page):
    # The key is server-only: no literal key, no direct googleapis call, and no
    # leftover client-side key plumbing.
    text = page.read_text()
    assert not _KEY_RE.search(text), f"{page.name} contains a literal API key"
    assert "sheets.googleapis.com" not in text, f"{page.name} calls Google directly"
    assert "SHEETS_API_KEY" not in text, f"{page.name} references the key global"
    assert "config.js" not in text, f"{page.name} still loads the old config.js"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_sheets_data_goes_through_the_proxy(page):
    assert "/api/sheets/" in page.read_text(), f"{page.name} has no proxy data calls"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_referenced_static_assets_exist(page):
    for rel in set(_ASSET_RE.findall(page.read_text())):
        assert (ROOT / rel).is_file(), f"{page.name} references missing asset {rel}"
