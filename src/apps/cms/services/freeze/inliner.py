"""Inline a page's CSS and assets into a self-contained document.

Ported from the standalone ``webfreeze`` tool (static path only):
- ``<link rel=stylesheet>`` -> inline ``<style>``
- CSS ``@import`` recursion + ``url(...)`` -> base64 data URIs
- ``<img>`` (incl. lazy ``data-src``) -> base64 data URIs

Sub-resource failures are logged and skipped (the resource is left as-is)
rather than aborting the whole freeze.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .cache import ResourceCache

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'url\((["\']?)(.*?)\1\)')
IMPORT_PATTERN = re.compile(r'@import\s+(?:url\()?["\']?([^"\')]+)["\']?\)?[^;]*;')


class Inliner:
    def __init__(self, cache: ResourceCache):
        self.cache = cache

    def inline_css(self, css_text: str, base_url: str) -> str:
        def replace_import(match):
            absolute_url = urljoin(base_url, match.group(1))
            try:
                _, content = self.cache.fetch(absolute_url)
                return self.inline_css(content.decode("utf-8", errors="ignore"), absolute_url)
            except Exception as exc:
                logger.info("freeze: skipped @import %s (%s)", absolute_url, exc)
                return ""

        css_text = IMPORT_PATTERN.sub(replace_import, css_text)

        def replace_url(match):
            quote = match.group(1)
            resource_url = match.group(2)
            if not resource_url or resource_url.startswith("data:"):
                return match.group(0)
            absolute_url = urljoin(base_url, resource_url)
            try:
                return f"url({quote}{self.cache.fetch_base64(absolute_url)}{quote})"
            except Exception as exc:
                logger.info("freeze: skipped url() %s (%s)", absolute_url, exc)
                return match.group(0)

        return URL_PATTERN.sub(replace_url, css_text)

    def process_soup(self, soup: BeautifulSoup, url: str) -> None:
        # Existing <style> tags: resolve nested @import / url().
        for style in soup.find_all("style"):
            if style.string:
                style.string = self.inline_css(style.string, url)

        # External stylesheets: fetch, inline, and replace the <link> with a <style>.
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if not href:
                continue
            absolute_url = urljoin(url, href)
            try:
                _, content = self.cache.fetch(absolute_url)
                inlined = self.inline_css(content.decode("utf-8", errors="ignore"), absolute_url)
                style_tag = soup.new_tag("style")
                style_tag.string = inlined
                link.replace_with(style_tag)
            except Exception as exc:
                logger.info("freeze: skipped stylesheet %s (%s)", absolute_url, exc)

        # Images (including lazy-loaded): inline as base64 data URIs.
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("lazy-src")
            if not src or src.startswith("data:"):
                continue
            absolute_url = urljoin(url, src)
            try:
                img["src"] = self.cache.fetch_base64(absolute_url)
                for attr in ("data-src", "data-original", "lazy-src", "srcset", "loading"):
                    if attr in img.attrs:
                        del img[attr]
            except Exception as exc:
                logger.info("freeze: skipped image %s (%s)", absolute_url, exc)
