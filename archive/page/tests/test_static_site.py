"""Invariants for the archived event pages.

The pages are Jinja children of templates/base.html, served at /<name>.html.
Their Sheets data flows through the same-origin ``/api/sheets/`` proxy in
app.py — the Google API key must never appear in (or be reachable from)
anything the browser receives, so the content checks run against the SERVED
output (which also covers base.html), not just the template source.
"""

import re
from pathlib import Path

import pytest
from app import app

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "templates" / "events").glob("*.html"))
BASE_TEMPLATE = ROOT / "templates" / "base.html"
SHARED_CSS = ROOT / "static" / "css" / "i2g-archive.css"

_ASSET_RE = re.compile(r"""(?:src|href)=["'](/?static/[^"'?#]+)["']""")
_KEY_RE = re.compile(r"AIzaSy[A-Za-z0-9_-]+")
_TITLE_RE = re.compile(r"<title>([^<]*)</title>")


@pytest.fixture(scope="module")
def serve():
    app.config.update(TESTING=True)
    with app.test_client() as client:
        pages = {p.stem: client.get(f"/{p.stem}.html") for p in PAGES}
        yield pages


def test_pages_were_discovered():
    # Guard against the glob silently matching nothing.
    assert len(PAGES) > 5


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_render_fully(serve, page):
    # Children must extend base.html and render with no leftover Jinja syntax.
    resp = serve[page.stem]
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    for delim in ("{{", "{%", "{#"):
        assert delim not in text, f"{page.name} served output still contains {delim}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_title_matches_filename(serve, page):
    # <name> is "<year>-<season>-..."; the title must agree with the filename.
    # (Guards against the old copy/paste bug where 2025-fall said "Fall 2024".)
    year, season = page.stem.split("-")[:2]
    text = serve[page.stem].get_data(as_text=True)
    title = _TITLE_RE.search(text).group(1)
    assert title == f"{season.capitalize()} {year} - Event | Innovate To Grow"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_api_key_or_direct_google_calls(serve, page):
    # The key is server-only: no literal key, no direct googleapis Sheets call,
    # and no leftover client-side key plumbing.
    text = serve[page.stem].get_data(as_text=True)
    assert not _KEY_RE.search(text), f"{page.name} contains a literal API key"
    assert "sheets.googleapis.com" not in text, f"{page.name} calls Google directly"
    assert "SHEETS_API_KEY" not in text, f"{page.name} references the key global"
    assert "config.js" not in text, f"{page.name} still loads the old config.js"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_sheets_data_goes_through_the_proxy(page):
    # Authoring invariant on the template source: every page fetches its
    # tables via the same-origin proxy.
    assert "/api/sheets/" in page.read_text(), f"{page.name} has no proxy data calls"


def test_page_grid_is_centered_as_a_whole():
    # The shared overrides moved from a per-page inline <style> into
    # i2g-archive.css; base.html must load it after the Drupal aggregates.
    css = SHARED_CSS.read_text()
    assert "body.i2g-center #main > .container" in css
    assert "margin-left: auto !important;" in css
    assert "margin-right: auto !important;" in css
    base = BASE_TEMPLATE.read_text()
    links = re.findall(r'href="(/static/css/[^"]+)"', base)
    assert links[-1] == "/static/css/i2g-archive.css", "shared CSS must load after the aggregates"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_program_intro_is_removed(serve, page):
    text = serve[page.stem].get_data(as_text=True)
    assert "The Innovate to Grow program" not in text
    assert 'alt="logo, icon"' not in text
    assert "Innovate to Grow (I2G) is a unique" not in text


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_userway_accessibility_widget_is_removed(serve, page):
    text = serve[page.stem].get_data(as_text=True)
    assert "userway.org" not in text
    assert 'data-account", "6Uvgvyrrph"' not in text


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_referenced_static_assets_exist(serve, page):
    # Scans the SERVED output, so base.html's renamed asset links are checked
    # alongside each page's own references.
    text = serve[page.stem].get_data(as_text=True)
    refs = set(_ASSET_RE.findall(text))
    assert refs, f"{page.name} references no static assets"
    for rel in refs:
        assert (ROOT / rel.lstrip("/")).is_file(), f"{page.name} references missing asset {rel}"
