"""Domain intelligence helpers: IDN/punycode, homograph, and typosquat detection.

Pure-Python (stdlib only); no network calls. Used by the sender and link checks
to catch look-alike domains that the plain brand-substring check misses, e.g.
``amaz0n.com`` (zero-for-o), ``paypaI.com`` (capital-i-for-l), or punycode IDNs.
"""

from __future__ import annotations

import unicodedata

# Confusable glyphs → ASCII letter they imitate. Applied before lower-casing so
# look-alikes such as a capital "I" (for "l") collapse onto the brand spelling.
_CONFUSABLES = {
    "0": "o",
    "1": "l",
    "|": "l",
    "!": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "$": "s",
    "@": "a",
    "vv": "w",
    "rn": "m",
    # Common Cyrillic/Greek look-alikes.
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "ѕ": "s",
    "х": "x",
    "і": "i",
    "ӏ": "l",
    "ο": "o",
}


def email_domain(address: str) -> str:
    """Return the lower-cased domain of an email address (``""`` if none)."""
    if not address or "@" not in address:
        return ""
    return address.rsplit("@", 1)[-1].strip().lower().rstrip(".")


def registrable_domain(domain: str) -> str:
    """Approximate eTLD+1 (last two labels) for comparing related hosts."""
    domain = (domain or "").strip().lower().rstrip(".")
    labels = [label for label in domain.split(".") if label]
    return ".".join(labels[-2:]) if len(labels) >= 2 else domain


def _registrable_label(domain: str) -> str:
    """The second-level label (the bit a brand owns), e.g. ``amazon`` of amazon.co.uk."""
    labels = [label for label in (domain or "").split(".") if label]
    if len(labels) >= 2:
        return labels[-2]
    return labels[0] if labels else ""


def is_punycode(domain: str) -> bool:
    return any(label.startswith("xn--") for label in (domain or "").lower().split("."))


def has_non_ascii(domain: str) -> bool:
    return any(ord(ch) > 127 for ch in (domain or ""))


def suspicious_idn_reason(domain: str) -> str | None:
    """Reason string when a domain uses punycode or raw non-ASCII (homograph risk)."""
    if not domain:
        return None
    if is_punycode(domain):
        return f"Domain {domain} uses punycode (xn--), a common homograph disguise"
    if has_non_ascii(domain):
        return f"Domain {domain} contains non-ASCII characters that can imitate a real domain"
    return None


def skeleton(value: str) -> str:
    """Collapse confusable glyphs onto a canonical ASCII spelling for comparison."""
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    for glyph, ascii_char in _CONFUSABLES.items():
        normalized = normalized.replace(glyph, ascii_char)
    return normalized.lower()


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def brand_lookalike(domain: str, brands: list[str]) -> str | None:
    """Reason string when ``domain`` impersonates a brand without being it.

    Catches confusable spellings (skeleton equals the brand) and single-edit
    typosquats (for brands of length >= 5, to avoid false positives on short
    brands like "ups"/"irs"). The exact, legitimate brand domain is never flagged.
    """
    label = _registrable_label(domain)
    if not label:
        return None
    label_skeleton = skeleton(label)
    for brand in brands:
        brand = (brand or "").strip().lower()
        # Only single-token brands map onto a domain label.
        if not brand or " " in brand or not brand.isalnum():
            continue
        if label == brand:
            return None  # legitimate exact match wins outright
        if label_skeleton == brand:
            return f'Domain "{domain}" imitates "{brand}" using look-alike characters'
        if len(brand) >= 5 and _levenshtein(label_skeleton, brand) == 1:
            return f'Domain "{domain}" closely resembles "{brand}" (possible typosquat)'
    return None
