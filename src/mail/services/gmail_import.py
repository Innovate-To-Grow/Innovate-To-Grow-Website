"""Helpers for importing recent Gmail sent-message HTML into campaigns."""

from __future__ import annotations

import base64
import logging
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build

from core.models import GoogleCredentialConfig

from .preview import HTML_MARKER

logger = logging.getLogger(__name__)

DEFAULT_GMAIL_MAILBOX = "i2g@g.ucmerced.edu"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailImportError(RuntimeError):
    """Raised when Gmail message import cannot be completed."""


def _get_gmail_service(mailbox: str = DEFAULT_GMAIL_MAILBOX):
    config = GoogleCredentialConfig.load()
    if not config.is_configured:
        raise GmailImportError("No active Google service account is configured.")

    try:
        credentials = service_account.Credentials.from_service_account_info(
            config.get_credentials_info(),
            scopes=[GMAIL_READONLY_SCOPE],
        ).with_subject(mailbox)
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)
    except Exception as exc:  # pragma: no cover - exercised via mocked tests
        logger.exception("Failed to initialize Gmail API client for mailbox %s.", mailbox)
        raise GmailImportError(f"Unable to connect to Gmail for {mailbox}.") from exc


def _decode_gmail_body(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")


def _extract_header(payload: dict[str, Any], header_name: str) -> str:
    for header in payload.get("headers", []) or []:
        if header.get("name", "").lower() == header_name.lower():
            return str(header.get("value", "")).strip()
    return ""


def _format_sent_at(header_value: str) -> str:
    if not header_value:
        return ""
    try:
        return parsedate_to_datetime(header_value).strftime("%Y-%m-%d %I:%M %p %Z")
    except (TypeError, ValueError, IndexError, OverflowError):
        return header_value


def _extract_html_from_payload(payload: dict[str, Any]) -> str:
    if not payload:
        return ""

    mime_type = str(payload.get("mimeType", "")).lower()
    body_data = (payload.get("body") or {}).get("data", "")
    if mime_type == "text/html" and body_data:
        return _decode_gmail_body(body_data)

    for part in payload.get("parts", []) or []:
        html = _extract_html_from_payload(part)
        if html:
            return html
    return ""


def _normalize_html_fragment(html: str) -> str:
    normalized = str(html or "").strip()
    if not normalized:
        return ""

    soup = BeautifulSoup(normalized, "html.parser")
    if soup.body is not None:
        body_html = "".join(str(child) for child in soup.body.contents).strip()
        if body_html:
            return body_html
    return normalized


def _get_full_message(service, message_id: str) -> dict[str, Any]:
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()


def list_recent_sent_messages(limit: int = 5, mailbox: str = DEFAULT_GMAIL_MAILBOX) -> list[dict[str, Any]]:
    """Return summaries for the most recent sent Gmail messages."""
    service = _get_gmail_service(mailbox)

    try:
        response = service.users().messages().list(userId="me", labelIds=["SENT"], maxResults=limit).execute()
        messages = response.get("messages", []) or []
        summaries: list[dict[str, Any]] = []

        for message in messages:
            full_message = _get_full_message(service, message["id"])
            payload = full_message.get("payload") or {}
            html = _extract_html_from_payload(payload)
            summaries.append(
                {
                    "message_id": full_message.get("id", message["id"]),
                    "subject": _extract_header(payload, "Subject") or "(No subject)",
                    "sent_at": _format_sent_at(_extract_header(payload, "Date")),
                    "snippet": full_message.get("snippet", ""),
                    "has_html": bool(_normalize_html_fragment(html)),
                }
            )

        return summaries
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised via mocked tests
        logger.exception("Failed to list recent sent Gmail messages for %s.", mailbox)
        raise GmailImportError("Failed to load recent sent Gmail messages.") from exc


def fetch_message_html_fragment(message_id: str, mailbox: str = DEFAULT_GMAIL_MAILBOX) -> str:
    """Fetch a Gmail message and return a wrapper-safe HTML fragment."""
    service = _get_gmail_service(mailbox)

    try:
        message = _get_full_message(service, message_id)
        payload = message.get("payload") or {}
        html = _normalize_html_fragment(_extract_html_from_payload(payload))
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised via mocked tests
        logger.exception("Failed to fetch Gmail message %s for %s.", message_id, mailbox)
        raise GmailImportError("Failed to fetch the selected Gmail message.") from exc

    if not html:
        raise GmailImportError("The selected Gmail message does not contain an HTML body.")
    return html


def import_message_into_campaign(campaign, message_id: str, mailbox: str = DEFAULT_GMAIL_MAILBOX) -> str:
    """Import a Gmail HTML message into the given draft campaign."""
    html_fragment = fetch_message_html_fragment(message_id, mailbox=mailbox)
    campaign.body = HTML_MARKER + html_fragment
    campaign.save(update_fields=["body", "updated_at"])
    return campaign.body
