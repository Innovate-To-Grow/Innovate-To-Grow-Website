"""Inbox backend that reads the I2G mailbox through Microsoft Graph instead of Gmail IMAP.

It is used whenever the active Microsoft Graph config grants read permission on its sending mailbox, and returns
the same dictionaries as the IMAP backend so the admin views and the scam detector do not change. The site only
issues GET requests (the Graph transport refuses anything else), so opening a message never marks it read in
Outlook.

A Graph message id is unique in the whole mailbox, not per folder, so a message also says whether it was sent from
the site's own address (``from_own_mailbox``): the views treat such a message as Sent mail whichever folder the
request named.
"""

import email
import email.policy
import logging
from datetime import datetime
from email.utils import parseaddr
from typing import Any

from bs4 import BeautifulSoup
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.mailbox import (
    GraphMailboxReader,
    GraphMessageNotFound,
    GraphReadBusy,
    GraphReadError,
)

from .connection import InboxBusy, InboxError
from .formatting import format_date

logger = logging.getLogger(__name__)


def active_reader() -> GraphMailboxReader | None:
    """A reader for the Graph sending mailbox when the scope grants read on it; otherwise None (use IMAP)."""
    graph = MicrosoftGraphProviderConfig.load()
    if not graph.is_configured:
        return None
    mailbox = graph.sender_mailbox(EmailServiceConfig.load().from_email)
    if not graph.allows(mailbox, "read"):
        return None
    return GraphMailboxReader(graph, mailbox)


def graph_inbox_active() -> bool:
    """Whether Mail -> Inbox reads the Microsoft Graph mailbox (rather than the Gmail import account)."""
    return active_reader() is not None


def list_messages(reader: GraphMailboxReader, *, folder: str, limit: int) -> list[dict[str, Any]]:
    try:
        messages = reader.list_messages(folder, limit)
    except GraphReadBusy as exc:
        raise InboxBusy(str(exc), exc.retry_after) from exc
    except GraphReadError as exc:
        raise InboxError(str(exc)) from exc
    own_addresses = _own_addresses(reader)
    return [_summary(message, own_addresses) for message in messages]


def fetch_message(reader: GraphMailboxReader, uid: str) -> dict[str, Any]:
    try:
        raw = reader.fetch_mime(uid)
    except GraphMessageNotFound as exc:
        raise InboxError("Message not found.") from exc
    except GraphReadBusy as exc:
        raise InboxBusy(str(exc), exc.retry_after) from exc
    except GraphReadError as exc:
        raise InboxError(str(exc)) from exc
    detail = _detail(uid, email.message_from_bytes(raw, policy=email.policy.default))
    detail["from_own_mailbox"] = detail["from_email"].strip().lower() in _own_addresses(reader)
    return detail


def _own_addresses(reader: GraphMailboxReader) -> frozenset[str]:
    """The site's own addresses: the mailbox read and the configured From address."""
    addresses = (reader.mailbox, EmailServiceConfig.load().from_email)
    return frozenset(str(address or "").strip().lower() for address in addresses) - {""}


def _summary(message: dict, own_addresses: frozenset[str] = frozenset()) -> dict[str, Any]:
    sender = (message.get("from") or {}).get("emailAddress") or {}
    snippet = " ".join(str(message.get("bodyPreview") or "").split())
    from_email = str(sender.get("address") or "")
    return {
        "uid": message["id"],
        "subject": str(message.get("subject") or "").strip() or "(No subject)",
        "from_name": str(sender.get("name") or ""),
        "from_email": from_email,
        "to": [_recipient(item) for item in message.get("toRecipients") or [] if isinstance(item, dict)],
        "date": _format_iso(message.get("receivedDateTime")),
        "snippet": snippet[:197].rstrip() + "..." if len(snippet) > 200 else snippet,
        "is_seen": bool(message.get("isRead")),
        "from_own_mailbox": from_email.strip().lower() in own_addresses,
    }


def _recipient(item: dict) -> dict[str, str]:
    address = item.get("emailAddress") or {}
    return {"name": str(address.get("name") or ""), "email": str(address.get("address") or "")}


def _format_iso(value) -> str:
    parsed = parse_datetime(str(value or ""))
    return format_date(timezone.localtime(parsed) if parsed and timezone.is_aware(parsed) else parsed)


def _detail(uid: str, message) -> dict[str, Any]:
    from_name, from_email = parseaddr(str(message.get("From", "")))
    html, text = _body(message, "html"), _body(message, "plain")
    return {
        "uid": uid,
        "subject": str(message.get("Subject", "") or "").strip() or "(No subject)",
        "from_name": from_name,
        "from_email": from_email,
        "to": [{"name": address.display_name, "email": address.addr_spec} for address in _addresses(message, "To")],
        "date": format_date(_message_date(message)),
        "html": html,
        "text": text or (BeautifulSoup(html, "html.parser").get_text("\n").strip() if html else ""),
        "message_id": str(message.get("Message-ID", "") or "").strip(),
        "references": str(message.get("References", "") or "").strip(),
        "reply_to": parseaddr(str(message.get("Reply-To", "")))[1].strip().lower(),
        "return_path": parseaddr(str(message.get("Return-Path", "")))[1].strip().lower(),
        "authentication_results": " ".join(str(value) for value in message.get_all("Authentication-Results", [])),
    }


def _body(message, subtype: str) -> str:
    try:
        part = message.get_body(preferencelist=(subtype,))
        return str(part.get_content()).strip() if part is not None else ""
    except (LookupError, ValueError, KeyError, AttributeError):
        logger.warning("Could not decode the %s body of a Graph inbox message.", subtype)
        return ""


def _addresses(message, header: str) -> list:
    try:
        value = message.get(header)
        return list(value.addresses) if value is not None else []
    except (AttributeError, ValueError, IndexError):
        return []


def _message_date(message) -> datetime | None:
    try:
        value = message.get("Date")
        parsed = value.datetime if value is not None else None
    except (AttributeError, ValueError, TypeError):
        return None
    return timezone.localtime(parsed) if parsed and timezone.is_aware(parsed) else parsed
