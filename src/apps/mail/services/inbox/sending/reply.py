import logging
import re
import unicodedata

from django.utils.html import escape

from apps.core.models import EmailServiceConfig
from apps.core.services.email import EmailDeliveryError, EmailMessage, deliver_email, email_tracking
from apps.core.services.email.inbound import LINK_PLACEHOLDER
from apps.core.utils.security import is_plain_address

from .senders import DEFAULT_SENDER, resolve_identity

logger = logging.getLogger(__name__)
REPLY_SEND_FAILURE_MESSAGE = "Failed to send reply. Please check server logs for details."
REPLY_DELIVERY_NOT_CONFIGURED = "Email delivery is not configured. Check Notification Delivery in admin."
REPLY_INVALID_ADDRESS_MESSAGE = "Use plain email addresses such as name@example.com in To and Cc."
REPLY_SENDER_UNAVAILABLE_MESSAGE = "That From address is not available. Reload the reply form and choose another."
# Where a link starts in the raw text, after the "_" or "~" marks (Markdown's emphasis) that may open right before it
# (a run of them is read once: the match starts at its first mark); ``_in_link`` reads where the link ends.
_LINK_START_RE = re.compile(r"(?i)(?<![_~])([_~]*)https?://")
# The ASCII a link takes: the printable characters but '"', "<" and ">".
_LINK_ASCII = frozenset(map(chr, range(0x21, 0x7F))) - set('"<>')
# Scripts written without spaces between words (Chinese, Japanese, Korean), by the start of their Unicode names.
_UNSPACED = ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "BOPOMOFO", "IDEOGRAPHIC", "FULLWIDTH", "HALFWIDTH")
# Never the last character of a link as written: the end of a sentence, a closing quote or backtick, a "*" (bold, a
# footnote). "_" and "~" can be (an id ending in "_"): one goes only when it closes the same mark right before the link.
_TRAILING = ".,;:!?'`*"
_OPENING = {")": "(", "]": "[", "}": "{"}


def _in_link(text: str, index: int) -> bool:
    """Whether ``text[index]`` goes on with the link before it: printable ASCII but '"', "<", ">" or the start of a
    "[sign-in link removed]"; a letter, digit or combining mark of any script (``…/wiki/Universität…``), never other
    punctuation (CJK, curly quotes), a symbol or a space. Chinese, Japanese or Korean text glued to the link's ASCII
    goes on with the sentence ("文件在<link>谢谢"), unless a part of the address starts there: after "/", "=", "#",
    "(" or "_" (``/wiki/加利福尼亚…``)."""
    char = text[index]
    if char.isascii():
        return char in _LINK_ASCII and not text.startswith(LINK_PLACEHOLDER, index)
    if unicodedata.category(char)[0] not in "LMN":
        return False
    before = text[index - 1]
    return not before.isascii() or before in "/=#(_" or not unicodedata.name(char, "").startswith(_UNSPACED)


def _link_end(url: str, opened: str = "") -> str:
    """``url`` without what ends the sentence around it (as Django's ``urlize`` trims): trailing punctuation and
    closing quotes, a closing bracket the link does not open, and the marks closing those ``opened`` right before it
    (``_link_``)."""
    marks = list(opened)
    while url:
        last = url[-1]
        unopened = last in _OPENING and url.count(_OPENING[last]) < url.count(last)
        if last in marks:
            marks.remove(last)
        elif last not in _TRAILING and not unopened:
            break
        url = url[:-1]
    return url


def _linkified(body_text: str) -> str:
    """``body_text`` escaped, its links as anchors: found in the raw text, so an "&" stays inside its link."""
    parts, start = [], 0
    for found in _LINK_START_RE.finditer(body_text):
        begin, end = found.end(1), found.end()
        if begin < start:
            continue  # inside the link before it, which carries this one (``…/web/2026/https://…``)
        while end < len(body_text) and _in_link(body_text, end):
            end += 1
        url = _link_end(body_text[begin:end], found.group(1))
        if url.endswith("://"):
            continue  # nothing but the scheme is left: it stays text
        safe = escape(url)
        parts += [escape(body_text[start:begin]), f'<a href="{safe}" style="color:#0f2d52;">{safe}</a>']
        start = begin + len(url)
    return "".join([*parts, escape(body_text[start:])])


def render_reply_html(body_text, original_from="", original_date="", quoted_text=""):
    from django.conf import settings
    from django.template.loader import render_to_string

    body_html = _linkified(str(body_text or "")).replace("\n", "<br>\n")
    # The quote sits in a "white-space: pre-wrap" block, so a line break there is one <br> (Outlook ignores pre-wrap).
    quoted = str(quoted_text or "").replace("\r\n", "\n").replace("\r", "\n")
    safe_quoted = escape(quoted).replace("\n", "<br>") if quoted else ""

    return render_to_string(
        "mail/email/reply_wrapper.html",
        {
            "body": body_html,
            "logo_url": f"{settings.STATIC_URL}images/i2glogo.png",
            "original_from": escape(original_from),
            "original_date": escape(original_date),
            "quoted_text": safe_quoted,
        },
    )


def send_reply(
    *,
    to_email: str,
    subject: str,
    reply_body: str,
    in_reply_to: str = "",
    references: str = "",
    original_from: str = "",
    original_date: str = "",
    quoted_text: str = "",
    cc_email: str = "",
    sender: str = DEFAULT_SENDER,
) -> str:
    """Send a reply From ``sender`` (a ``senders.SendIdentity`` key; ``default``: Notification Delivery). Returns ""
    when the provider accepted it, else the error to show."""
    config = EmailServiceConfig.load()
    cc_list = [email.strip() for email in cc_email.split(",") if email.strip()] if cc_email else []
    # The To address comes from the original sender's From header, so it may be crafted.
    if not all(is_plain_address(address) for address in (to_email, *cc_list)):
        return REPLY_INVALID_ADDRESS_MESSAGE
    html = render_reply_html(reply_body, original_from, original_date, quoted_text)
    message = _build_reply_message(
        config=config,
        to_email=to_email,
        subject=subject,
        html=html,
        cc_list=cc_list,
        in_reply_to=in_reply_to,
        references=references,
    )

    if (sender or DEFAULT_SENDER) != DEFAULT_SENDER:
        identity = resolve_identity(sender)
        if identity is None:
            return REPLY_SENDER_UNAVAILABLE_MESSAGE
        return _deliver_reply(config=identity.delivery_config(config), to_email=to_email, message=message)

    if not config.delivery_configured:
        return REPLY_DELIVERY_NOT_CONFIGURED

    return _deliver_reply(config=config, to_email=to_email, message=message)


def _deliver_reply(*, config, to_email, message) -> str:
    try:
        with email_tracking(category="inbox_reply"):
            deliver_email(message, config=config)
        return ""
    except EmailDeliveryError:
        logger.exception("Failed to send reply to %s.", to_email)
        return REPLY_SEND_FAILURE_MESSAGE


def _build_reply_message(
    *,
    config,
    to_email: str,
    subject: str,
    html: str,
    cc_list: list[str],
    in_reply_to: str,
    references: str,
):
    del config
    headers = {}
    if in_reply_to:
        headers["In-Reply-To"] = in_reply_to
    if references:
        headers["References"] = references
    return EmailMessage(subject=subject, to=(to_email,), cc=tuple(cc_list), html_body=html, headers=headers)
