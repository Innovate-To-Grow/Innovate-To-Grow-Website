"""Link and redirect rewriting: Legacy URLs onto the CloudFront viewer origin."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..origin.policies import (
    InvalidLegacyPath,
    PathDecision,
    canonicalize_legacy_path,
    classify_legacy_path,
)
from ..origin.query import filter_query_string

LEGACY_PUBLIC_HOSTS = {
    "35.86.48.145",
    "legacy.i2g.ucmerced.edu",
}


@dataclass(frozen=True)
class RewrittenURL:
    value: str
    blocked: bool = False
    internal: bool = False


class InvalidLegacyURL(ValueError):
    """Raised when an origin-provided URL cannot be parsed safely."""


def _internal_url_parts(value: str, current_path: str, origin_host: str):
    stripped = value.strip()
    if not stripped or stripped.startswith("#"):
        return None

    try:
        parsed = urlsplit(stripped)
    except ValueError as exc:
        raise InvalidLegacyURL("Legacy origin returned an invalid URL.") from exc
    scheme = parsed.scheme.lower()
    if scheme in {"javascript", "vbscript"}:
        return False
    if scheme and scheme not in {"http", "https"}:
        return None

    base = f"http://{origin_host}{current_path}"
    try:
        resolved = urlsplit(urljoin(base, stripped))
        hostname = (resolved.hostname or "").lower()
    except ValueError as exc:
        raise InvalidLegacyURL("Legacy origin returned an invalid URL.") from exc
    internal_hosts = {*LEGACY_PUBLIC_HOSTS, origin_host.lower()}
    return resolved if hostname in internal_hosts else None


def rewrite_document_url(value: str, current_path: str, origin_host: str, viewer_base_url: str) -> RewrittenURL:
    try:
        parts = _internal_url_parts(value, current_path, origin_host)
    except InvalidLegacyURL:
        return RewrittenURL("#", blocked=True)
    if parts is False:
        return RewrittenURL("#", blocked=True)
    if parts is None:
        return RewrittenURL(value)

    try:
        canonical_path = canonicalize_legacy_path(parts.path)
        decision = classify_legacy_path(canonical_path)
    except InvalidLegacyPath:
        return RewrittenURL("#", blocked=True, internal=True)
    if decision is not PathDecision.ALLOW:
        return RewrittenURL("#", blocked=True, internal=True)
    rewritten = urlunsplit(
        (
            "https",
            urlsplit(viewer_base_url).netloc,
            canonical_path,
            filter_query_string(parts.query),
            parts.fragment,
        )
    )
    return RewrittenURL(rewritten, internal=True)


def rewrite_location(value: str, current_path: str, origin_host: str, viewer_base_url: str) -> str:
    """Keep external redirects external and route every internal redirect via CloudFront."""

    parts = _internal_url_parts(value, current_path, origin_host)
    if parts is False:
        return viewer_base_url
    if parts is None:
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise InvalidLegacyURL("Legacy origin returned an invalid redirect URL.") from exc
        return value if parsed.scheme in {"http", "https"} else viewer_base_url
    try:
        canonical_path = canonicalize_legacy_path(parts.path)
    except InvalidLegacyPath:
        return viewer_base_url
    return urlunsplit(
        (
            "https",
            urlsplit(viewer_base_url).netloc,
            canonical_path,
            filter_query_string(parts.query),
            parts.fragment,
        )
    )
