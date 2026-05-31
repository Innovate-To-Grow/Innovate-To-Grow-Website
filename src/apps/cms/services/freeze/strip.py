"""Remove scripts and unwanted sections from a parsed page before inlining."""

from __future__ import annotations

from bs4 import BeautifulSoup

from .config import REMOVAL_PRESETS
from .exceptions import FreezeError

# Resource hints that would trigger background fetches / re-enable behavior.
_DROPPED_LINK_RELS = {"preload", "prefetch", "modulepreload", "dns-prefetch", "preconnect"}


def strip_scripts_and_handlers(soup: BeautifulSoup) -> None:
    """Neutralize all scripting so the frozen snapshot is inert.

    The frozen document is only ever served into a sandboxed iframe under a tight
    CSP (no ``script-src``), so scripts cannot execute regardless. This pass is
    defense-in-depth: it removes them at capture time as well.
    """
    for tag in soup.find_all(["script", "noscript"]):
        tag.decompose()
    # Inline event handlers (onclick, onload, ...).
    for tag in soup.find_all(True):
        for attr in [a for a in tag.attrs if a.lower().startswith("on")]:
            del tag[attr]
    # Resource hints / meta refresh that would trigger navigation or fetches.
    for link in soup.find_all("link"):
        rels = {r.lower() for r in (link.get("rel") or [])}
        if rels & _DROPPED_LINK_RELS:
            link.decompose()
    for meta in soup.find_all("meta"):
        if (meta.get("http-equiv") or "").lower() == "refresh":
            meta.decompose()


def apply_removals(soup: BeautifulSoup, *, remove_presets=(), extra_selectors=()) -> None:
    """Decompose elements matching the chosen presets and free-form selectors."""
    selectors: list[str] = []
    for preset in remove_presets:
        selectors.extend(REMOVAL_PRESETS.get(preset, []))
    selectors.extend(extra_selectors)

    for raw in selectors:
        selector = (raw or "").strip()
        if not selector:
            continue
        try:
            matches = soup.select(selector)
        except Exception as exc:  # invalid CSS selector from admin free-form input
            raise FreezeError(f"Invalid CSS selector {selector!r}: {exc}") from exc
        for element in matches:
            element.decompose()


def serialize(soup: BeautifulSoup) -> str:
    """Serialize the soup to a self-contained HTML string with a DOCTYPE.

    ``formatter=None`` preserves CSS verbatim (e.g. child combinators ``a > b``
    and attribute selectors) which "minimal" escaping would corrupt. The output
    is untrusted foreign HTML by design — its security boundary is the sandboxed
    iframe + CSP at render time, not output escaping.
    """
    body = soup.encode(formatter=None).decode("utf-8")
    if not body.strip().lower().startswith("<!doctype"):
        body = f"<!DOCTYPE html>\n{body}"
    return body
