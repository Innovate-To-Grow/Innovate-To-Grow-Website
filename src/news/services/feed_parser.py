# noinspection PyPep8Naming
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen

FEED_URL = "https://news.ucmerced.edu/taxonomy/term/221/all/feed"
DC_NS = "{http://purl.org/dc/elements/1.1/}"


def fetch_feed(url: str = FEED_URL) -> bytes:
    req = Request(url, headers={"User-Agent": "ITG-NewsSync/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_feed_items(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for item_el in root.iter("item"):
        item = {
            "title": _text(item_el, "title"),
            "link": _text(item_el, "link"),
            "description": _text(item_el, "description"),
            "pub_date": _text(item_el, "pubDate"),
            "creator": _text(item_el, f"{DC_NS}creator"),
            "guid": _text(item_el, "guid"),
        }
        items.append(item)
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
