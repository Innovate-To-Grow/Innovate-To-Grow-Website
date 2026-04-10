"""Inbox viewer and reply service using Gmail IMAP + AWS SES."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from bs4 import BeautifulSoup
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from imap_tools import AND, MailBox

from core.models import EmailServiceConfig, GmailImportConfig

logger = logging.getLogger(__name__)

INBOX_LIST_CACHE_KEY = "inbox:list"
INBOX_LIMIT_CHOICES = [15, 30, 50, 100]
INBOX_LIST_CACHE_TTL = 300  # 5 minutes
INBOX_MSG_CACHE_PREFIX = "inbox:msg:"
INBOX_MSG_CACHE_TTL = 1800  # 30 minutes


class InboxError(RuntimeError):
    """Raised when an inbox operation cannot be completed."""


def _get_gmail_config() -> GmailImportConfig:
    try:
        config = GmailImportConfig.load()
    except (OperationalError, ProgrammingError) as exc:
        raise InboxError("Gmail configuration is unavailable. Run the latest migrations first.") from exc
    if not config.is_configured:
        raise InboxError("No active Gmail import account is configured.")
    return config


def _resolve_mailbox(mailbox: str | None = None) -> str:
    from .gmail_import import resolve_gmail_mailbox

    return resolve_gmail_mailbox(mailbox)


@contextmanager
def _open_inbox(mailbox: str | None = None):
    """Context manager that opens an IMAP connection to the INBOX folder."""
    config = _get_gmail_config()
    resolved_mailbox = _resolve_mailbox(mailbox or config.mailbox)
    try:
        with MailBox(config.imap_host).login(
            resolved_mailbox,
            config.gmail_password,
            initial_folder="INBOX",
        ) as client:
            yield client
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to connect to Gmail IMAP inbox for %s.", resolved_mailbox)
        raise InboxError(f"Unable to connect to inbox for {resolved_mailbox}.") from exc


def _format_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %I:%M %p").strip()
    if value:
        return str(value)
    return ""


def _build_snippet(message: Any) -> str:
    html = str(getattr(message, "html", "") or "").strip()
    text = str(getattr(message, "text", "") or "").strip()
    source = html or text
    if not source:
        return ""
    snippet = " ".join(BeautifulSoup(source, "html.parser").get_text(" ").split())
    if len(snippet) > 200:
        return snippet[:197].rstrip() + "..."
    return snippet


def _extract_from(message: Any) -> tuple[str, str]:
    """Return (from_name, from_email) from a message."""
    from_values = getattr(message, "from_values", None)
    if from_values:
        return str(getattr(from_values, "name", "") or ""), str(getattr(from_values, "email", "") or "")
    from_str = str(getattr(message, "from_", "") or "")
    return "", from_str


def _extract_to(message: Any) -> list[dict[str, str]]:
    """Return list of {name, email} dicts for To recipients."""
    to_values = getattr(message, "to_values", None) or []
    return [{"name": str(getattr(v, "name", "") or ""), "email": str(getattr(v, "email", "") or "")} for v in to_values]


def list_inbox_messages(
    limit: int = 30, mailbox: str | None = None, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Return summaries for the most recent inbox messages."""
    cache_key = f"{INBOX_LIST_CACHE_KEY}:{limit}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        with _open_inbox(mailbox=mailbox) as client:
            messages = list(client.fetch(limit=limit, reverse=True, mark_seen=False, bulk=True))
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to list inbox messages.")
        raise InboxError("Failed to load inbox messages.") from exc

    results: list[dict[str, Any]] = []
    for msg in messages:
        from_name, from_email = _extract_from(msg)
        flags = set(getattr(msg, "flags", ()) or ())
        results.append(
            {
                "uid": str(getattr(msg, "uid", "") or ""),
                "subject": str(getattr(msg, "subject", "") or "").strip() or "(No subject)",
                "from_name": from_name,
                "from_email": from_email,
                "date": _format_date(getattr(msg, "date", None)),
                "snippet": _build_snippet(msg),
                "is_seen": "\\Seen" in flags,
            }
        )

    cache.set(cache_key, results, INBOX_LIST_CACHE_TTL)
    return results


def fetch_inbox_message(uid: str, mailbox: str | None = None) -> dict[str, Any]:
    """Fetch a single inbox message by UID with full details.

    First fetch hits IMAP with mark_seen=True. Subsequent fetches serve from cache.
    """
    cache_key = f"{INBOX_MSG_CACHE_PREFIX}{uid}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        with _open_inbox(mailbox=mailbox) as client:
            for msg in client.fetch(AND(uid=uid), limit=1, mark_seen=True, bulk=False):
                from_name, from_email = _extract_from(msg)
                headers = getattr(msg, "headers", {}) or {}
                message_id = ""
                message_id_list = headers.get("message-id", [])
                if message_id_list:
                    message_id = str(message_id_list[0])
                references_list = headers.get("references", [])
                references = str(references_list[0]) if references_list else ""

                html = str(getattr(msg, "html", "") or "").strip()
                text = str(getattr(msg, "text", "") or "").strip()

                result = {
                    "uid": str(getattr(msg, "uid", "") or ""),
                    "subject": str(getattr(msg, "subject", "") or "").strip() or "(No subject)",
                    "from_name": from_name,
                    "from_email": from_email,
                    "to": _extract_to(msg),
                    "date": _format_date(getattr(msg, "date", None)),
                    "html": html,
                    "text": text,
                    "message_id": message_id,
                    "references": references,
                }
                cache.set(cache_key, result, INBOX_MSG_CACHE_TTL)
                _update_list_cache_seen(uid)
                return result
            raise InboxError("Message not found.")
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch inbox message uid=%s.", uid)
        raise InboxError("Failed to fetch the message.") from exc


def _update_list_cache_seen(uid: str) -> None:
    """Mark a message as seen in all cached inbox lists (if present)."""
    for limit in INBOX_LIMIT_CHOICES:
        cache_key = f"{INBOX_LIST_CACHE_KEY}:{limit}"
        cached_list = cache.get(cache_key)
        if cached_list is None:
            continue
        for msg in cached_list:
            if msg["uid"] == uid:
                msg["is_seen"] = True
                break
        cache.set(cache_key, cached_list, INBOX_LIST_CACHE_TTL)


def render_reply_html(body_text, original_from="", original_date="", quoted_text=""):
    """Wrap reply body in the standard email layout with optional quoted original."""
    import re

    from django.conf import settings
    from django.template.loader import render_to_string
    from django.utils.html import escape

    # Convert plain text reply to HTML
    escaped = escape(body_text)
    escaped = re.sub(r"(https?://[^\s<>&]+)", r'<a href="\1" style="color:#0f2d52;">\1</a>', escaped)
    body_html = escaped.replace("\n", "<br>\n")

    logo_url = f"{settings.STATIC_URL}images/i2glogo.png"

    # Escape quoted text but preserve line breaks
    safe_quoted = ""
    if quoted_text:
        safe_quoted = escape(quoted_text).replace("\n", "<br>\n")

    return render_to_string(
        "mail/email/reply_wrapper.html",
        {
            "body": body_html,
            "logo_url": logo_url,
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
) -> str:
    """
    Send a reply email via SES with the standard email layout.

    Returns empty string on success, error message on failure.
    """
    config = EmailServiceConfig.load()
    if not config.ses_configured:
        return "SES is not configured. Cannot send reply."

    wrapped_html = render_reply_html(
        reply_body,
        original_from=original_from,
        original_date=original_date,
        quoted_text=quoted_text,
    )

    cc_list = [e.strip() for e in cc_email.split(",") if e.strip()] if cc_email else []

    try:
        import boto3

        client = boto3.client(
            "ses",
            region_name=config.ses_region,
            aws_access_key_id=config.ses_access_key_id,
            aws_secret_access_key=config.ses_secret_access_key,
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.source_address
        msg["To"] = to_email
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        msg.attach(MIMEText(wrapped_html, "html", "utf-8"))

        destinations = [to_email] + cc_list
        client.send_raw_email(
            Source=config.source_address,
            Destinations=destinations,
            RawMessage={"Data": msg.as_string()},
        )
        return ""
    except Exception as exc:
        logger.exception("Failed to send reply to %s.", to_email)
        return str(exc)
