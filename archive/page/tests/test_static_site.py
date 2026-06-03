"""Smoke checks for the static archive — no server, just the built HTML.

Guards the conversion from the old Flask app: every event page must be fully
rendered (no leftover Jinja), must wire the gitignored Sheets key via
``static/config.js`` (never an inline key), and must only reference static
assets that actually exist on disk.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted(ROOT.glob("*.html"))

# Static assets referenced from HTML, e.g. src="static/js/x.js" / href="static/css/y.css"
_ASSET_RE = re.compile(r"""(?:src|href)=["'](static/[^"'?#]+)["']""")
_KEY_RE = re.compile(r"AIzaSy[A-Za-z0-9_-]+")


def test_pages_were_discovered():
    # Guard against the glob silently matching nothing.
    assert len(PAGES) > 5


def test_config_example_is_present():
    # The real key lives in the gitignored static/config.js; the example is the
    # committed template that documents it.
    assert (ROOT / "static" / "config.example.js").is_file()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_unrendered_jinja(page):
    text = page.read_text()
    assert "{{" not in text and "{%" not in text, f"{page.name} still contains Jinja"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_inline_api_key(page):
    # The key must come from window.SHEETS_API_KEY, never be baked into the page.
    assert not _KEY_RE.search(page.read_text()), f"{page.name} contains a literal API key"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_wires_the_key_global(page):
    text = page.read_text()
    assert "static/config.js" in text, f"{page.name} does not load static/config.js"
    assert "window.SHEETS_API_KEY" in text, f"{page.name} never reads window.SHEETS_API_KEY"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_referenced_static_assets_exist(page):
    for rel in set(_ASSET_RE.findall(page.read_text())):
        assert (ROOT / rel).is_file(), f"{page.name} references missing asset {rel}"
