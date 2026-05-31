"""Freeze an external page into a self-contained HTML document."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from .cache import ResourceCache
from .config import MAX_TOTAL_FROZEN_BYTES, USER_AGENT
from .exceptions import FreezeError
from .fetcher import fetch_html
from .inliner import Inliner
from .strip import apply_removals, serialize, strip_scripts_and_handlers

logger = logging.getLogger(__name__)


@dataclass
class FrozenResult:
    final_url: str
    title: str
    html: str
    byte_size: int


def _base_url(soup: BeautifulSoup, fallback: str) -> str:
    base = soup.find("base")
    if base and base.get("href"):
        return base["href"]
    return fallback


def _page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()[:300]
    return ""


def freeze_url(url: str, *, remove_presets=(), extra_selectors=()) -> FrozenResult:
    """Fetch ``url``, strip scripts + chosen sections, inline CSS/assets, return a self-contained doc.

    Raises BlockedURLError (SSRF guard), FreezeFetchError (fetch failure), or
    FreezeError (bad selector / oversized result).
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    try:
        final_url, raw_html = fetch_html(url, session)
        soup = BeautifulSoup(raw_html, "html.parser")

        # Order matters: drop scripts + unwanted sections BEFORE inlining so we
        # don't waste fetches base64-encoding assets we're about to delete.
        strip_scripts_and_handlers(soup)
        apply_removals(soup, remove_presets=remove_presets, extra_selectors=extra_selectors)

        title = _page_title(soup)
        Inliner(ResourceCache(session)).process_soup(soup, _base_url(soup, final_url))

        html = serialize(soup)
        byte_size = len(html.encode("utf-8"))
        if byte_size > MAX_TOTAL_FROZEN_BYTES:
            raise FreezeError(
                f"Frozen document is too large ({byte_size:,} bytes > {MAX_TOTAL_FROZEN_BYTES:,}). "
                "Try removing large sections or media before importing."
            )
        return FrozenResult(final_url=final_url, title=title, html=html, byte_size=byte_size)
    finally:
        session.close()
