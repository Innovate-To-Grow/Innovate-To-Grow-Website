import re
from urllib.parse import unquote

from django.core.exceptions import ValidationError

from apps.cms.models.content.cms.cms_page import normalize_cms_route, validate_cms_route

URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


INVALID_PERCENT_ENCODING_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


LEGACY_ROUTE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~+-]+$")


def normalize_and_validate_cms_page_route(route: str | None) -> str:
    """Normalize a strict CMS page route, including editor slash cleanup."""

    raw_route = route or ""
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_route):
        raise ValidationError("Paths cannot contain control characters.")
    if URL_SCHEME_RE.match(raw_route.strip()):
        raise ValidationError("Use a site-relative path, not a full URL.")
    if "?" in raw_route or "#" in raw_route:
        raise ValidationError("Paths cannot include a query string or fragment.")
    if "\\" in raw_route:
        raise ValidationError("Paths cannot contain backslashes.")
    return validate_cms_route(normalize_cms_route(raw_route))


def normalize_and_validate_route(route: str | None) -> str:
    """Normalize a strict redirect destination route."""

    raw_route = route or ""
    if raw_route.strip().startswith("//"):
        raise ValidationError("Protocol-relative paths are not allowed.")
    return normalize_and_validate_cms_page_route(raw_route)


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _check_legacy_path_shape(raw_route: str, trimmed: str) -> None:
    if _has_control_characters(raw_route):
        raise ValidationError("Paths cannot contain control characters.")
    if URL_SCHEME_RE.match(trimmed):
        raise ValidationError("Use a site-relative path, not a full URL.")
    if trimmed.startswith("//"):
        raise ValidationError("Protocol-relative paths are not allowed.")
    if "?" in trimmed or "#" in trimmed:
        raise ValidationError("Paths cannot include a query string or fragment.")
    if "\\" in trimmed:
        raise ValidationError("Paths cannot contain backslashes.")


def _decode_legacy_segment(encoded_segment: str) -> str:
    if INVALID_PERCENT_ENCODING_RE.search(encoded_segment):
        raise ValidationError("Path contains invalid percent encoding.")
    try:
        segment = unquote(encoded_segment, errors="strict")
    except UnicodeDecodeError:
        raise ValidationError("Path contains invalid percent encoding.")
    if segment in {".", ".."}:
        raise ValidationError("Dot path segments are not allowed.")
    if "/" in segment or "\\" in segment:
        raise ValidationError("Encoded slash or backslash characters are not allowed.")
    if _has_control_characters(segment):
        raise ValidationError("Paths cannot contain control characters.")
    if not LEGACY_ROUTE_SEGMENT_RE.fullmatch(segment):
        raise ValidationError(
            "Legacy path segments may use letters, numbers, dots, hyphens, underscores, tildes, or plus signs."
        )
    return segment


def normalize_and_validate_legacy_source(route: str | None) -> str:
    """Normalize a safe legacy path while allowing common URL punctuation."""

    raw_route = route or ""
    trimmed = raw_route.strip()
    _check_legacy_path_shape(raw_route, trimmed)
    segments = [_decode_legacy_segment(segment) for segment in trimmed.split("/") if segment]
    return "/" + "/".join(segments) if segments else "/"
