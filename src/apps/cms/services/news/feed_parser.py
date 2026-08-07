import html
import http.client
import re
import time
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit

from defusedxml import ElementTree as ET

from .url_guard import read_bounded_response, safe_urlopen

FEED_URL = "https://news.ucmerced.edu/taxonomy/term/221/all/feed"
MAX_FEED_BYTES = 2 * 1024 * 1024
NEWS_SYNC_USER_AGENT = "InnovateToGrow-NewsSync/1.0 (+https://i2g.ucmerced.edu/)"
NEWS_SYNC_FROM = "i2g@ucmerced.edu"
FEED_REQUEST_HEADERS = {
    # Identify this as a feed synchronizer instead of impersonating a browser;
    # From provides an operator contact without putting an email in every log's UA.
    "User-Agent": NEWS_SYNC_USER_AGENT,
    "From": NEWS_SYNC_FROM,
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1",
}
_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_FETCH_TIMEOUT_SECONDS = 30
_FETCH_MAX_ATTEMPTS = 3
_FETCH_RETRY_BASE_SECONDS = 0.25
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


def _retryable_http_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _wait_before_retry(attempt: int) -> None:
    time.sleep(_FETCH_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))


def fetch_feed(url: str = FEED_URL) -> bytes:
    # ``url`` is admin-configurable (NewsFeedSource.feed_url); fetch it through
    # the SSRF guard so it can't reach internal/loopback hosts or file://.
    for attempt in range(1, _FETCH_MAX_ATTEMPTS + 1):
        try:
            with safe_urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS, headers=FEED_REQUEST_HEADERS) as resp:
                return read_bounded_response(resp, max_bytes=MAX_FEED_BYTES, label="RSS feed")
        except HTTPError as exc:
            retryable = _retryable_http_status(exc.code)
            if retryable and attempt < _FETCH_MAX_ATTEMPTS:
                exc.close()
                _wait_before_retry(attempt)
                continue
            try:
                error = _http_error_details(exc, attempts=attempt, retryable=retryable)
            finally:
                exc.close()
            raise error from exc
        except (URLError, OSError, http.client.HTTPException) as exc:
            if attempt < _FETCH_MAX_ATTEMPTS:
                _wait_before_retry(attempt)
                continue
            raise FeedFetchError(
                status=None,
                final_url=url,
                reason=getattr(exc, "reason", None) or exc or "transport failure",
                retryable=True,
                attempts=attempt,
            ) from exc

    raise AssertionError("RSS retry loop exited unexpectedly.")


def parse_feed_items(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for item_el in root.iter("item"):
        items.append(
            {
                "title": _text(item_el, "title"),
                "link": _text(item_el, "link"),
                "description": _text(item_el, "description"),
                "pub_date": _text(item_el, "pubDate"),
                "creator": _text(item_el, f"{_DC_NS}creator"),
                "guid": _text(item_el, "guid"),
            }
        )
    return items


def extract_image_url(html: str) -> str:
    if not html:
        return ""
    match = re.search(r'<img[^>]+src="([^"]+)"', html)
    return match.group(1) if match else ""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paragraphs: list[str] = []
        self._current: list[str] = []
        self._in_p = False

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._in_p = True
            self._current = []

    def handle_endtag(self, tag):
        if tag == "p" and self._in_p:
            self._in_p = False
            text = "".join(self._current).strip()
            if text:
                self.paragraphs.append(text)

    def handle_data(self, data):
        if self._in_p:
            self._current.append(data)


def extract_summary(html: str, max_length: int = 200) -> str:
    if not html:
        return ""
    extractor = _TextExtractor()
    extractor.feed(html)
    for paragraph in extractor.paragraphs:
        if len(paragraph) > 20:
            if len(paragraph) > max_length:
                return paragraph[:max_length].rsplit(" ", 1)[0] + "..."
            return paragraph
    return ""


def parse_pub_date(date_str: str):
    if not date_str:
        return None
    return parsedate_to_datetime(date_str)


def _text(element, tag: str) -> str:
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else ""
