"""The Graph JSON ``sendMail`` body, for messages that must leave no copy in the sender mailbox's Sent Items.

A MIME ``sendMail`` request always saves the message to Sent Items; only the JSON form takes
``saveToSentItems``. The JSON form carries one body (the HTML body when the message has one, otherwise the text
body), the recipients including Bcc, Reply-To, file attachments (inline ones by Content-ID) and custom headers, but
Graph accepts only custom headers whose names start with ``x-`` (``internetMessageHeaders``). Any other caller
header (``List-Unsubscribe``, ``In-Reply-To``, ``References``) is left out and its name logged, so only messages
that do not depend on such headers should be sent this way.
"""

import base64
import json
import logging
import re
from email.utils import parseaddr

from ..contracts import EmailAttachment, EmailMessage
from ..exceptions import PermanentEmailDeliveryError
from ..mime import PROTECTED_HEADERS, attachment_content_type

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/json"
FILE_ATTACHMENT_TYPE = "#microsoft.graph.fileAttachment"
_HEADER_NAME_RE = re.compile(r"[A-Za-z0-9-]{1,76}")
_CUSTOM_HEADER_RE = re.compile(r"[Xx]-[A-Za-z0-9-]{1,74}")


def send_mail_body(message: EmailMessage, *, from_email: str, from_name: str = "") -> bytes:
    """The UTF-8 JSON request body: the message with ``saveToSentItems`` false. Problems are permanent errors."""
    if not message.envelope_recipients:
        raise PermanentEmailDeliveryError("Email has no recipients.")
    if not message.text_body and not message.html_body:
        raise PermanentEmailDeliveryError("Email has no body.")
    if not message.html_body and any(item.disposition == "inline" for item in message.attachments):
        raise PermanentEmailDeliveryError("Inline email attachments require an HTML body.")
    graph_message = {
        "subject": message.subject,
        "body": _body(message),
        "from": _address(from_email, from_name),
        "toRecipients": _recipients(message.to),
    }
    for key, addresses in (("ccRecipients", message.cc), ("bccRecipients", message.bcc), ("replyTo", message.reply_to)):
        if addresses:
            graph_message[key] = _recipients(addresses)
    if message.attachments:
        graph_message["attachments"] = [_attachment(item) for item in message.attachments]
    headers = _custom_headers(message.headers)
    if headers:
        graph_message["internetMessageHeaders"] = headers
    return json.dumps({"message": graph_message, "saveToSentItems": False}, ensure_ascii=False).encode("utf-8")


def _body(message: EmailMessage) -> dict[str, str]:
    if message.html_body:
        return {"contentType": "HTML", "content": message.html_body}
    return {"contentType": "Text", "content": message.text_body}


def _address(address: str, name: str = "") -> dict:
    email_address = {"address": address, "name": name} if name else {"address": address}
    return {"emailAddress": email_address}


def _recipients(values) -> list[dict]:
    """Graph recipients from plain or ``Name <address>`` strings; anything else is refused."""
    recipients = []
    for value in values:
        text = str(value)
        name, address = parseaddr(text)
        if "@" not in address or "\r" in text or "\n" in text:
            raise PermanentEmailDeliveryError("An email recipient address is invalid.")
        recipients.append(_address(address, name))
    return recipients


def _attachment(attachment: EmailAttachment) -> dict:
    attachment_content_type(attachment.content_type)
    item = {
        "@odata.type": FILE_ATTACHMENT_TYPE,
        "name": attachment.filename,
        "contentType": attachment.content_type,
        "contentBytes": base64.b64encode(attachment.content).decode("ascii"),
    }
    if attachment.disposition == "inline":
        # The HTML refers to it as ``cid:<content id>``; Graph takes the id without the angle brackets.
        item["isInline"] = True
        item["contentId"] = (attachment.content_id or attachment.filename).strip("<>")
    elif attachment.content_id:
        item["contentId"] = attachment.content_id.strip("<>")
    return item


def _custom_headers(headers: dict[str, str]) -> list[dict[str, str]]:
    carried, dropped = [], []
    for name, value in headers.items():
        text = str(value)
        if not _HEADER_NAME_RE.fullmatch(str(name)) or "\r" in text or "\n" in text:
            raise PermanentEmailDeliveryError("An email header is malformed.")
        if name.lower() in PROTECTED_HEADERS:
            raise PermanentEmailDeliveryError(f"Email header {name!r} is managed by the delivery service.")
        if _CUSTOM_HEADER_RE.fullmatch(name):
            carried.append({"name": name, "value": text})
        else:
            dropped.append(name)
    if dropped:
        logger.warning(
            "Microsoft Graph JSON sendMail cannot carry these headers, so they were left out: %s", ", ".join(dropped)
        )
    return carried
