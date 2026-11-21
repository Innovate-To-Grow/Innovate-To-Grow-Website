"""What reading one inbound message yields, the limits it is read within, and the text of its HTML."""

import codecs
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup, NavigableString

from apps.core.services.email.telemetry import text

MAX_PARTS = 500
MAX_DEPTH = 12
MAX_ATTACHED_MESSAGES = 5
TEXT_PART_MAX_BYTES = 4 * 1024 * 1024
ATTACHED_TEXT_MAX_CHARS = 64 * 1024
HTML_TO_TEXT_MAX_CHARS = 256 * 1024
NESTED_TYPES = frozenset({"message/rfc822", "message/global"})
# A saved message attached as a file, whatever type it is sent as: read like an attached message, never kept raw.
MESSAGE_FILE_SUFFIXES = (".eml",)
# Machine-readable parts of a report: the bounce processor reads them; they are neither body nor attachment here.
REPORT_PARTS = frozenset(
    {
        "message/delivery-status",
        "message/global-delivery-status",
        "message/disposition-notification",
        "message/global-disposition-notification",
        "text/rfc822-headers",
        "message/global-headers",
    }
)
BODY_TYPES = ("text/plain", "text/html")
_PART_ERRORS = (AssertionError, LookupError, TypeError, ValueError, UnicodeError, IndexError, AttributeError)
# Codecs no mail program writes text in: punycode decodes in quadratic time (a crafted 4 MB body would stall the
# import for minutes), and the escape codecs turn plain bytes into other characters. Such text is read as UTF-8.
_ODD_CODECS = frozenset({"punycode", "idna", "unicode-escape", "raw-unicode-escape"})
# Elements shown on lines of their own, and a table's cells (side by side); any other element (inline formatting, a
# link) is read on with the text around it.
_BLOCKS = frozenset(
    {
        "address", "article", "aside", "blockquote", "caption", "center", "dd", "div", "dl", "dt", "figcaption",
        "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
        "section", "table", "tbody", "tfoot", "thead", "title", "tr", "ul",
    }
)  # fmt: skip
_CELLS = frozenset({"td", "th"})
# Marks for a block's edges and a line break while HTML is laid out (dropped from the HTML first).
_EDGE, _BREAK = "\x00", "\x01"
_SPACES_RE = re.compile(r"[ \t\n\r\f]+")  # HTML's white space: a no-break space is text
_EDGES_RE = re.compile(r"[ \x00]*\x00[ \x00]*")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def text_codec(charset: str) -> str:
    """The codec to read text declared in ``charset``: Python's name for it, else UTF-8."""
    try:
        name = codecs.lookup(charset).name if charset else "utf-8"
    except _PART_ERRORS:
        return "utf-8"
    return "utf-8" if name in _ODD_CODECS else name


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    content_id: str = ""
    is_inline: bool = False
    data: bytes | None = None
    size: int = 0
    charset: str = ""


@dataclass
class ParsedMessage:
    headers: dict
    message_id: str = ""
    in_reply_to: str = ""
    references: list = field(default_factory=list)
    subject: str = ""
    from_address: str = ""
    from_name: str = ""
    to: list = field(default_factory=list)
    cc: list = field(default_factory=list)
    reply_to: str = ""
    date_header: str = ""
    sent_at: datetime | None = None
    content_type: str = "text/plain"
    report_type: str = ""
    text: str = ""
    html: str = ""
    attachments: list = field(default_factory=list)
    attached_messages: list = field(default_factory=list)
    attached_dropped: int = 0
    has_calendar: bool = False
    truncated: bool = False
    incomplete: bool = False

    def text_head(self, chars: int = 4096) -> str:
        return (self.text or html_to_text(self.html))[:chars]

    def fingerprint(self) -> str:
        """One message, however often it arrives: its Message-ID, or (none) its sender, date, subject and text."""
        if self.message_id:
            basis = f"message-id\n{self.message_id.lower()}"
        else:
            basis = "\n".join(
                ("content", self.from_address, self.date_header, text.normalize_subject(self.subject), self.text[:4096])
            )
        return hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()


def html_to_text(html: str, limit: int = HTML_TO_TEXT_MAX_CHARS) -> str:
    """The text of ``html`` laid out as a mail program shows it: a line for each block (a paragraph, a list item, a
    table row, …) and each <br>, a row's cells side by side, and inline formatting and links read on with the line
    (so a link that <span>s split reads whole); at most one empty line in a row."""
    if not html:
        return ""
    soup = BeautifulSoup(html[:limit].replace(_EDGE, "").replace(_BREAK, ""), "html.parser")
    for pre in soup.find_all("pre"):  # its line breaks are the text's own
        for string in pre.find_all(string=lambda found: type(found) is NavigableString):
            string.replace_with(string.replace("\n", _BREAK))
    for element in soup.find_all(["br", *_BLOCKS, *_CELLS]):
        if element.name == "br":
            element.replace_with(_BREAK)
        elif element.name in _CELLS:
            element.insert_after(" ")
        else:
            element.insert_before(_EDGE)
            element.insert_after(_EDGE)
    laid_out = _EDGES_RE.sub("\n", _SPACES_RE.sub(" ", soup.get_text())).replace(_BREAK, "\n")
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(line.strip() for line in laid_out.split("\n"))).strip()
