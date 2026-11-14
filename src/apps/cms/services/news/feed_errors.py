"""What a failed feed fetch reports: ``FeedFetchError`` and the sanitized status, content type, URL and CDN
reference it carries."""

import html
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit

_ERROR_BODY_BYTES = 4096
_ERROR_TEXT_LENGTH = 300
_ERROR_URL_LENGTH = 1000
_AKAMAI_REFERENCE_RE = re.compile(r"\bReference\s*#\s*([A-Za-z0-9._-]{1,200})", re.IGNORECASE)
_EDGESUITE_REFERENCE_RE = re.compile(r"errors\.edgesuite\.net/([A-Za-z0-9._-]{1,200})", re.IGNORECASE)
_CONTENT_TYPE_RE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+")


class FeedFetchError(RuntimeError):
    """Safe, structured details for a failed outbound RSS request.

    The exception is persisted by the sync caller, so it deliberately omits the
    response body and strips URL credentials, query strings, and fragments.
    """

    def __init__(
        self,
        *,
        status: int | None,
        final_url: str,
        content_type: str = "",
        akamai_reference: str = "",
        reason: str = "",
        retryable: bool,
        attempts: int,
    ):
        self.status = status
        self.final_url = _sanitize_url(final_url)
        self.content_type = _sanitize_content_type(content_type)
        self.akamai_reference = _clean_text(akamai_reference, max_length=200)
        self.reason = _clean_text(reason, max_length=_ERROR_TEXT_LENGTH)
        self.retryable = retryable
        self.attempts = attempts
        super().__init__(self._message())

    def _message(self) -> str:
        details = []
        if self.status is not None:
            details.append(f"status={self.status}")
        details.append(f"url={self.final_url}")
        if self.content_type:
            details.append(f"content_type={self.content_type}")
        if self.akamai_reference:
            details.append(f"akamai_reference={self.akamai_reference}")
        if self.reason:
            details.append(f"reason={self.reason}")
        details.append(f"attempts={self.attempts}")
        return f"RSS feed fetch failed ({', '.join(details)})"


def _clean_text(value, *, max_length: int) -> str:
    """Collapse control/whitespace characters and cap persisted diagnostics."""
    if value is None:
        return ""
    cleaned = " ".join(str(value).split())
    return cleaned[:max_length]


def _sanitize_url(url: str) -> str:
    """Keep a useful request target without credentials, query data, or fragments."""
    try:
        parts = urlsplit(str(url))
        host = parts.hostname
        if parts.scheme not in {"http", "https"} or not host:
            return "<redacted-url>"
        if ":" in host:
            host = f"[{host}]"
        try:
            port = parts.port
        except ValueError:
            return "<redacted-url>"
        netloc = f"{host}:{port}" if port is not None else host
        sanitized = urlunsplit((parts.scheme, netloc, parts.path or "/", "", ""))
    except (TypeError, ValueError):
        return "<redacted-url>"
    return _clean_text(sanitized, max_length=_ERROR_URL_LENGTH)


def _sanitize_content_type(value: str) -> str:
    cleaned = _clean_text(value, max_length=200)
    match = _CONTENT_TYPE_RE.match(cleaned)
    return match.group(0).lower() if match else ""


def _header_value(headers, name: str) -> str:
    if headers is None:
        return ""
    try:
        return headers.get(name, "") or ""
    except (AttributeError, TypeError):
        return ""


def _akamai_reference_from_error(error: HTTPError) -> str:
    """Read a small error-page prefix and retain only Akamai's opaque reference."""
    try:
        payload = error.read(_ERROR_BODY_BYTES + 1)[:_ERROR_BODY_BYTES]
    except (OSError, ValueError):
        return ""
    decoded = html.unescape(payload.decode("utf-8", errors="replace"))
    for pattern in (_AKAMAI_REFERENCE_RE, _EDGESUITE_REFERENCE_RE):
        match = pattern.search(decoded)
        if match:
            return match.group(1)
    return ""


def _http_error_details(error: HTTPError, *, attempts: int, retryable: bool) -> FeedFetchError:
    content_type = _header_value(error.headers, "Content-Type")
    reference = _akamai_reference_from_error(error)
    return FeedFetchError(
        status=error.code,
        final_url=error.geturl(),
        content_type=content_type,
        akamai_reference=reference,
        reason=error.reason,
        retryable=retryable,
        attempts=attempts,
    )
