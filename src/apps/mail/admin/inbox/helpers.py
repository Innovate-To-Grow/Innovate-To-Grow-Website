"""Inbox admin helper functions."""

import hashlib
import json
from html import escape
from urllib.parse import urlencode

from django.core.cache import cache

from apps.mail.services.inbox.reading.connection import INBOX_MSG_CACHE_TTL

from . import services as inbox_api

# A message's security assessment is kept as long as the opened message itself (``INBOX_MSG_CACHE_TTL``), so opening
# it again repeats neither the rule scoring nor the AI review of a medium-risk message.
ASSESSMENT_CACHE_PREFIX = "inbox:assessment:"
ASSESSMENT_CACHE_TTL = INBOX_MSG_CACHE_TTL
# What the assessment reads of a message (``scam_detector``); a message whose content changed is assessed again.
_ASSESSED_FIELDS = (
    "account",
    "uid",
    "subject",
    "from_name",
    "from_email",
    "reply_to",
    "return_path",
    "authentication_results",
    "from_own_mailbox",
    "html",
    "text",
)


def message_load_error(exc) -> str:
    """What staff see when a message cannot be shown: when to try again while reads are held back, else the generic
    message (other errors may name hosts or accounts)."""
    return str(exc) if isinstance(exc, inbox_api.InboxBusy) else inbox_api.INBOX_MESSAGE_ERROR_MESSAGE


def cached_assessment(msg: dict, *, folder: str) -> dict:
    """``assess_email`` of an opened message, cached at this call site (the shared scam detector is unchanged)."""
    fields = {name: msg.get(name) for name in _ASSESSED_FIELDS}
    digest = hashlib.sha256(json.dumps([folder, fields], sort_keys=True, default=str).encode()).hexdigest()
    key = f"{ASSESSMENT_CACHE_PREFIX}{digest}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    assessment = inbox_api.assess_email(msg, folder=folder)
    cache.set(key, assessment, ASSESSMENT_CACHE_TTL)
    return assessment


def inbox_account_summary(accounts: list, selected: str) -> dict[str, str]:
    """Which mailbox the inbox shows and where it is read from (Microsoft Graph or Gmail IMAP)."""
    for account in accounts:
        if account.key == selected:
            return {"account": account.address, "source_label": account.source_label, "source": account.source}
    if not accounts:
        return {"account": "Not configured", "source_label": "Source", "source": "N/A"}
    if len(accounts) == 1:
        only = accounts[0]
        return {"account": only.address, "source_label": only.source_label, "source": only.source}
    return {
        "account": f"All accounts ({len(accounts)})",
        "source_label": "Sources",
        "source": ", ".join(sorted({account.source for account in accounts})),
    }


def parse_limit(request) -> int:
    """Parse and validate the requested inbox limit."""
    try:
        value = int(request.GET.get("limit", inbox_api.INBOX_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return inbox_api.INBOX_DEFAULT_LIMIT
    return value if value in inbox_api.INBOX_LIMIT_CHOICES else inbox_api.INBOX_DEFAULT_LIMIT


def parse_folder(request) -> str:
    """Parse and validate the requested inbox folder (INBOX or SENT)."""
    folder = str(request.GET.get("folder", inbox_api.INBOX_FOLDER)).upper()
    return folder if folder in inbox_api.INBOX_FOLDER_CHOICES else inbox_api.INBOX_FOLDER


def parse_account(request, *, default: str = "") -> str:
    """The requested inbox account key (``?account=``). The inbox services accept only a configured account's key,
    so this only trims it; ``default`` stands in when none is named."""
    value = str(request.GET.get("account", "") or "").strip()
    return value[:300] or default


def with_query(url: str, **params) -> str:
    """``url`` with the non-empty ``params`` as its query string (``urlencode``d)."""
    query = urlencode({key: value for key, value in params.items() if value})
    return f"{url}?{query}" if query else url


def message_body_html(msg: dict) -> str:
    """Return sanitized text fallback when a message has no HTML body."""
    if msg["html"]:
        return msg["html"]
    return f"<pre>{escape(msg['text'] or '')}</pre>"


def build_reply_references(msg: dict) -> str:
    """Build email References for a reply."""
    reply_references = msg.get("references", "")
    if msg.get("message_id"):
        if reply_references:
            return f"{reply_references} {msg['message_id']}"
        return msg["message_id"]
    return reply_references


def build_original_from(msg: dict) -> str:
    """Build display sender for quoted reply context."""
    original_from = msg["from_name"] or msg["from_email"]
    if msg["from_name"]:
        return f"{msg['from_name']} <{msg['from_email']}>"
    return original_from


def build_reply_subject(subject: str) -> str:
    """Prefix a subject with Re: when needed."""
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"
