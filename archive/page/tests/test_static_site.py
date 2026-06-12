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


def _page_sources(page):
    """Template source plus any page-owned extracted assets it references.

    Pages may keep their CSS/JS inline or extracted under static/{css,js}/events/
    — invariants about what the browser ends up running must cover both.
    """
    text = page.read_text()
    sources = [text]
    for rel in re.findall(r"""(?:src|href)=["']/(static/(?:js|css)/events/[^"'?#]+)["']""", text):
        sources.append((ROOT / rel).read_text())
    return sources


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_api_key_or_direct_google_calls(serve, page):
    # The key is server-only: no literal key, no direct googleapis Sheets call,
    # and no leftover client-side key plumbing — in the served page AND in the
    # page's extracted assets.
    for text in [serve[page.stem].get_data(as_text=True), *_page_sources(page)]:
        assert not _KEY_RE.search(text), f"{page.name} contains a literal API key"
        assert "sheets.googleapis.com" not in text, f"{page.name} calls Google directly"
        assert "SHEETS_API_KEY" not in text, f"{page.name} references the key global"
        assert "config.js" not in text, f"{page.name} still loads the old config.js"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_sheets_data_goes_through_the_proxy(page):
    # Authoring invariant: every page fetches its tables via the same-origin
    # proxy, whether its loader scripts are inline or extracted.
    assert any("/api/sheets/" in s for s in _page_sources(page)), f"{page.name} has no proxy data calls"


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


def test_2022_fall_sheet_cells_are_text_and_urls_are_validated():
    sources = _page_sources(ROOT / "templates" / "events" / "2022-fall-event.html")
    js = "\n".join(sources)
    assert "document.createTextNode(value == null ? \"\" : String(value))" in js
    assert "$.fn.dataTable.render.text()" in js
    assert "escapeSheetText(d.Abstract)" in js
    assert "escapeSheetText(d[\"Student Names\"])" in js
    assert "url.protocol === \"http:\" || url.protocol === \"https:\"" in js
    assert ".href = data.values" not in js
    assert ".prepend(data.values" not in js
    assert "<td>' + d.Abstract + '</td>" not in js
    assert "<td>' + d[\"Student Names\"] + '</td>" not in js


def test_base_template_loads_shared_sheet_safe_helpers():
    # The escaping helpers must be available to every page before any event
    # script runs, so they live in base.html's <head>.
    base = BASE_TEMPLATE.read_text()
    assert "/static/js/sheet-safe.js" in base
    shared = (ROOT / "static" / "js" / "sheet-safe.js").read_text()
    for fn in ("function escapeSheetText", "function prependSheetText", "function safeSheetUrl"):
        assert fn in shared, f"sheet-safe.js missing {fn}"


def _active_code_lines(js_text):
    """Yield JS lines that are not whole-line // comments (the only comment
    style the event scripts use around the sink call sites)."""
    for line in js_text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        yield line


# Regression guard for the confirmed stored/DOM-XSS finding: Google-Sheets cells
# (fetched via /api/sheets/) must never be injected as raw HTML or used as an
# unchecked link target. Every event page's JS must route them through the
# shared escaping helpers. Mirrors the hardening already proven on 2022-fall.
@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_event_scripts_have_no_raw_sheet_sinks(page):
    for source in _page_sources(page):
        for line in _active_code_lines(source):
            # (A) sheet row cell concatenated into HTML without escaping.
            if ("escapeSheetText" not in line) and re.search(r"\+\s*d(?:\.[A-Za-z_]|\[)", line):
                if "</td>" in line or "<td>" in line or "<" in line:
                    raise AssertionError(f"{page.name}: unescaped sheet cell in HTML: {line.strip()}")
            # (B) jQuery .prepend() of sheet data parses it as HTML.
            assert ".prepend(data.values" not in line, f"{page.name}: raw .prepend of sheet data: {line.strip()}"
            # (C) sheet value assigned to a link href without scheme validation.
            assert not re.search(r"\.href\s*=\s*(?:data\.values|d\[|d\.)", line), (
                f"{page.name}: unvalidated sheet URL assigned to href: {line.strip()}"
            )


# DataTables does not auto-escape cell content; a column bound to a sheet field
# (`"data": "Field"`) must opt into the text renderer. Columns that show no sheet
# data use `"data": null`. This catches the control-column gap that the line-based
# sink scan above cannot see (the binding spans multiple lines).
@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_datatables_columns_escape_sheet_fields(page):
    for source in _page_sources(page):
        if ".DataTable(" not in source:
            continue
        # Column objects are flat (no nested braces), so a non-greedy {...} match
        # isolates each one.
        for column in re.findall(r"\{[^{}]*\}", source):
            if re.search(r'"data"\s*:\s*"', column) and '"render"' not in column:
                raise AssertionError(
                    f"{page.name}: DataTables column binds a sheet field without a text renderer: "
                    f"{' '.join(column.split())}"
                )
