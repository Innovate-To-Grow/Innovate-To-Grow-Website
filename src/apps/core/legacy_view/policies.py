"""Audited path and query-string policy for the read-only gateway."""

from __future__ import annotations

import re
from enum import Enum
from urllib.parse import parse_qsl, unquote, urlencode

MAX_PATH_LENGTH = 2048
MAX_QUERY_LENGTH = 2048
MAX_QUERY_FIELDS = 50


class InvalidLegacyPath(ValueError):
    """Raised when a path cannot be forwarded without ambiguous decoding."""


class PathDecision(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    UNKNOWN = "unknown"


# These routes were audited against archive/legacy/webpages.zip. They render
# historical/informational templates and do not mutate Flask, SQLite, or Sheets
# state on GET.
_INFORMATION_PATHS = {
    "/",
    "/2014-sponsors",
    "/2015-sponsors",
    "/2020-fall-post-event",
    "/2021-fall-event",
    "/2021-spring-event",
    "/2022-fall-event",
    "/2022-spring-event",
    "/2023-fall-event",
    "/2023-spring-event",
    "/2024-fall-event",
    "/2024-spring-event",
    "/2025-fall-event",
    "/2025-spring-event",
    "/about",
    "/about_engsl",
    "/acknowledgement",
    "/attendees",
    "/capstone-purchasing-reimbursement",
    "/contact-us",
    "/engineering-capstone",
    "/event",
    "/faqs",
    "/ferpa",
    "/home-during-event",
    "/home-post-event",
    "/i2g-project-sponsor-acknowledgement",
    "/i2g-student-agreement",
    "/i2g-students-preparation",
    "/judges",
    "/judging",
    "/partnership",
    "/past-events",
    "/past-projects",
    "/privacy",
    "/projects",
    "/projects-teams",
    "/sample-proposals",
    "/schedule",
    "/software-capstone",
    "/sponsorship",
    "/students",
    "/template",
    "/template-email-team-students",
    "/video-preparation",
    "/current-projects",
}

_READ_ONLY_API_PATHS = {
    "/api/current-projects",
    "/api/schedule-data",
}

# Flask-Admin exposes some model/custom views outside /admin. Keep them in this
# denylist even though the positive allowlist already fails closed.
_BLOCKED_PREFIXES = {
    "/admin",
    "/catch_bounces",
    "/confirm",
    "/contact",
    "/documentation",
    "/edit_form",
    "/event-registration",
    "/events",
    "/full-registration",
    "/info-form",
    "/manual_email",
    "/membership",
    "/otp",
    "/project-submission",
    "/prospects",
    "/resend",
    "/resend-page",
    "/signup",
    "/tracking_pixel",
    "/update",
    "/user",
}

_BLOCKED_STATIC_PATHS = {
    "/static/images/tracking_pixel.png",
    "/static/js/js-siteimprove.js",
    "/static/js/recaptcha-api.js",
}

_UUID_PATH_PATTERN = re.compile(
    r"^/past-projects/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_ALLOWED_QUERY_KEYS = {
    "_",
    "filter",
    "format",
    "order",
    "page",
    "q",
    "query",
    "search",
    "semester",
    "sort",
    "team",
    "track",
    "year",
}


def canonicalize_legacy_path(raw_path: str) -> str:
    """Decode once-to-stability and reject traversal or separator ambiguity."""

    if not isinstance(raw_path, str) or len(raw_path) > MAX_PATH_LENGTH:
        raise InvalidLegacyPath("Legacy path is invalid.")

    decoded = raw_path
    for _iteration in range(3):
        next_value = unquote(decoded, errors="strict")
        if next_value == decoded:
            break
        decoded = next_value
    else:
        if unquote(decoded, errors="strict") != decoded:
            raise InvalidLegacyPath("Legacy path has excessive encoding.")

    if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
        raise InvalidLegacyPath("Legacy path contains control characters.")
    if "\\" in decoded or "//" in decoded:
        raise InvalidLegacyPath("Legacy path contains an ambiguous separator.")

    decoded = decoded.lstrip("/")
    segments = decoded.split("/") if decoded else []
    if any(segment in {".", ".."} for segment in segments):
        raise InvalidLegacyPath("Legacy path contains traversal segments.")
    return f"/{decoded}" if decoded else "/"


def _matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def classify_legacy_path(canonical_path: str) -> PathDecision:
    """Return the audited disposition for a canonical absolute path."""

    path = canonical_path.lower()
    if any(_matches_prefix(path, prefix) for prefix in _BLOCKED_PREFIXES):
        return PathDecision.BLOCK
    # /event is public information, while /event/ and descendants are the
    # Flask-Admin EventModelView endpoint.
    if path.startswith("/event/") or path == "/static/admin" or path.startswith("/static/admin/"):
        return PathDecision.BLOCK
    if path in _BLOCKED_STATIC_PATHS:
        return PathDecision.BLOCK
    if path in _INFORMATION_PATHS or path in _READ_ONLY_API_PATHS:
        return PathDecision.ALLOW
    if path.startswith("/static/") and len(path) > len("/static/"):
        return PathDecision.ALLOW
    if _UUID_PATH_PATTERN.fullmatch(path):
        return PathDecision.ALLOW
    return PathDecision.UNKNOWN


def filter_query_string(raw_query_string: str) -> str:
    """Forward only bounded, presentation-only query parameters."""

    if not raw_query_string or len(raw_query_string) > MAX_QUERY_LENGTH:
        return ""
    try:
        pairs = parse_qsl(
            raw_query_string,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=MAX_QUERY_FIELDS,
        )
    except (UnicodeDecodeError, ValueError):
        return ""
    filtered = [(key, value) for key, value in pairs if key in _ALLOWED_QUERY_KEYS]
    return urlencode(filtered, doseq=True)
