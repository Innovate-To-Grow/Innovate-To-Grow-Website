"""Fake IMAP answers on the wire: the inbox list's ``UID SEARCH`` and raw ``UID FETCH`` (``reading.imap_list``).

A fake message is a ``SimpleNamespace`` shaped like an ``imap_tools`` message (``uid``, ``subject``, ``from_values``,
``to_values``, ``date``, ``html``, ``text``, ``flags``, ``headers``; ``attachments=True`` adds one). It is turned
into the header and text Gmail would return, so the real response parser and summary code run in the tests.
"""

import email.policy
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from types import SimpleNamespace

from apps.mail.services.inbox.reading.imap_list import LIST_TEXT_BYTES

PLAIN_STRUCTURE = b'("text" "plain" ("charset" "utf-8") NIL NIL "7bit" 5 1 NIL NIL NIL)'
ATTACHMENT_STRUCTURE = (
    b'(("text" "plain" ("charset" "utf-8") NIL NIL "7bit" 5 1 NIL NIL NIL)'
    b'("application" "pdf" ("name" "a.pdf") NIL NIL "base64" 10 NIL ("attachment" ("filename" "a.pdf")) NIL) '
    b'"mixed" ("boundary" "b1") NIL NIL)'
)


def _text(value) -> str:
    # Some fakes are MagicMocks: an attribute they never set is not text.
    return value if isinstance(value, str) else ""


def message_bytes(message) -> tuple[bytes, bytes]:
    """``(header, text)`` of a fake message as ``BODY[HEADER]`` and ``BODY[TEXT]`` return them."""
    mail = EmailMessage(policy=email.policy.SMTP)
    sender = getattr(message, "from_values", None)
    if sender:
        mail["From"] = formataddr((_text(sender.name), _text(sender.email)))
    elif _text(getattr(message, "from_", "")):
        mail["From"] = message.from_
    recipients = [
        formataddr((_text(item.name), _text(item.email))) for item in getattr(message, "to_values", None) or []
    ]
    if recipients:
        mail["To"] = ", ".join(recipients)
    if _text(getattr(message, "subject", "")):
        mail["Subject"] = message.subject
    date = getattr(message, "date", None)
    if isinstance(date, datetime):
        mail["Date"] = format_datetime(date if date.tzinfo else date.astimezone())
    for name, values in (getattr(message, "headers", None) or {}).items():
        for value in values:
            mail[name] = value
    html, text = _text(getattr(message, "html", "")), _text(getattr(message, "text", ""))
    if html and text:
        mail.set_content(text)
        mail.add_alternative(html, subtype="html")
    else:
        mail.set_content(html or text, subtype="html" if html else "plain")
    header, _, body = mail.as_bytes().partition(b"\r\n\r\n")
    return header + b"\r\n\r\n", body


def fetch_response(messages, uids) -> list:
    """The ``imaplib`` data of a ``UID FETCH`` of ``uids`` (in mailbox order, as servers answer)."""
    wanted, data = {str(uid) for uid in uids}, []
    for seq, message in enumerate(messages, start=1):
        if str(message.uid) not in wanted:
            continue
        header, text = message_bytes(message)
        text = text[:LIST_TEXT_BYTES]
        flags = " ".join(getattr(message, "flags", ()) or ()).encode()
        structure = ATTACHMENT_STRUCTURE if getattr(message, "attachments", False) is True else PLAIN_STRUCTURE
        prefix = b"%d (UID %s FLAGS (%s) BODYSTRUCTURE %s BODY[HEADER] {%d}" % (
            seq,
            str(message.uid).encode(),
            flags,
            structure,
            len(header),
        )
        data.extend([(prefix, header), (b" BODY[TEXT]<0> {%d}" % len(text), text), b")"])
    return data


def wire(client, messages):
    """Make a MagicMock ``imap_tools`` client answer the list's SEARCH and FETCH over ``messages``; returns the
    ``WireClient`` that records them."""
    fake = WireClient(messages)
    client.uids.side_effect = fake.uids
    client.client.uid.side_effect = fake._uid
    return fake


class WireClient:
    """A logged-in ``imap_tools`` mailbox over fake messages: the list's ``uids`` + raw ``UID FETCH``, and
    ``fetch`` (opening one message) returning the fake message itself."""

    def __init__(self, messages, *, present=None):
        self.messages = list(messages)
        self.present = present  # UIDs the FETCH still finds (None: all); a SEARCH lists every message
        self.searches, self.fetched, self.opened = [], [], []
        self.client = SimpleNamespace(uid=self._uid)

    def uids(self, criteria="ALL", *args, **kwargs):
        self.searches.append(str(criteria))
        return [str(message.uid) for message in self.messages]

    def _uid(self, command, uid_set, parts):
        requested = uid_set.split(",")
        self.fetched.append((command, requested, parts))
        found = [uid for uid in requested if self.present is None or uid in self.present]
        return "OK", fetch_response(self.messages, found)

    def fetch(self, criteria="ALL", **kwargs):
        self.opened.append((str(criteria), kwargs))
        return iter(self.messages)
