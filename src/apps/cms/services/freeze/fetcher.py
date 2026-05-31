"""Fetch the raw HTML of an external page (static / server-rendered only)."""

from __future__ import annotations

from .config import FETCH_TIMEOUT, MAX_DOCUMENT_BYTES
from .exceptions import FreezeFetchError
from .ssrf import BlockedURLError, guarded_get


def fetch_html(url: str, session) -> tuple[str, str]:
    """Return ``(final_url, html)`` for the given URL.

    Raises BlockedURLError if the SSRF guard rejects the URL (propagated as-is so
    the admin sees a clear "blocked" message) or FreezeFetchError on any other
    transport/HTTP failure.
    """
    try:
        resp = guarded_get(session, url, timeout=FETCH_TIMEOUT, max_bytes=MAX_DOCUMENT_BYTES)
    except BlockedURLError:
        raise
    except Exception as exc:  # translate any transport error into a clean freeze error
        raise FreezeFetchError(f"Could not fetch {url}: {exc}") from exc

    if resp.status_code >= 400:
        raise FreezeFetchError(f"Source returned HTTP {resp.status_code} for {url}.")

    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.url, resp.text
