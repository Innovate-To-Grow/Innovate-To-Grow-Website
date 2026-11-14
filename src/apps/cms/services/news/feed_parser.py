import http.client
import re
import time
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError

from defusedxml import ElementTree as ET

from .feed_errors import FeedFetchError, _http_error_details
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
