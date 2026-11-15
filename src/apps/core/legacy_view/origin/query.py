"""Audited query-string policy for the read-only gateway: the only query keys the Legacy origin may receive."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode

MAX_QUERY_LENGTH = 2048
MAX_QUERY_FIELDS = 50

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
