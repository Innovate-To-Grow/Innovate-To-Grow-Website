"""Cached, SSRF-guarded fetcher for sub-resources (CSS, images, fonts).

Ported from the standalone ``webfreeze`` ResourceCache, but every fetch routes
through :func:`guarded_get` and is capped at ``MAX_ASSET_BYTES``. Callers (the
inliner) treat any failure here as "leave the resource as-is", so raising plain
``ValueError`` on HTTP/size errors is sufficient.
"""

from __future__ import annotations

import base64

from .config import FETCH_TIMEOUT, MAX_ASSET_BYTES
from .ssrf import guarded_get


class ResourceCache:
    def __init__(self, session):
        self.session = session
        self._cache: dict[str, tuple[str, bytes]] = {}

    def fetch(self, url: str) -> tuple[str, bytes]:
        if url in self._cache:
            return self._cache[url]
        resp = guarded_get(self.session, url, timeout=FETCH_TIMEOUT, max_bytes=MAX_ASSET_BYTES)
        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code} for {url}")
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        content = resp.content
        self._cache[url] = (content_type, content)
        return content_type, content

    def fetch_base64(self, url: str) -> str:
        content_type, content = self.fetch(url)
        b64 = base64.b64encode(content).decode("ascii")
        return f"data:{content_type or 'application/octet-stream'};base64,{b64}"
