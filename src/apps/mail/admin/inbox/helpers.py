"""Inbox admin helper functions."""

from html import escape

from apps.core.utils.access import user_can_access_app

from . import services as inbox_api


def message_load_error(exc) -> str:
    """What staff see when a message cannot be shown: when to try again while reads are held back, else the generic
    message (other errors may name hosts or accounts)."""
    return str(exc) if isinstance(exc, inbox_api.InboxBusy) else inbox_api.INBOX_MESSAGE_ERROR_MESSAGE


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


def sent_mail_restricted(user) -> bool:
    """Whether *user* may not read Sent mail: staff granted the Mail app (and superusers) may; anyone else may not
    while the inbox reads the Graph mailbox, or while the Gmail account it reads is one the site sends as through the
    Gmail API.

    That folder holds what the site sends: Graph keeps what carries no credential flag there (campaigns, replies),
    and Gmail keeps a copy of everything, sign-in codes included. The list and the message view leave the site's
    tagged credential mail out of Sent for every reader (``apps.mail.services.inbox.messages``), so links and codes
    stay hidden. When the backend cannot be resolved, the answer is "restricted".
    """
    if user_can_access_app(user, "mail"):
        return False
    try:
        return inbox_api.graph_inbox_active() or inbox_api.gmail_sent_copies_kept()
    except Exception:
        inbox_api.logger.exception("Could not resolve the inbox backend; Sent mail stays restricted.")
        return True


def sent_mail_denied(request, folder: str, msg: dict | None = None) -> bool:
    """Whether the request reaches Sent mail (the folder, or a message from the site's own address) it may not read."""
    is_sent_mail = folder == inbox_api.SENT_FOLDER or bool(msg and msg.get("from_own_mailbox"))
    return is_sent_mail and sent_mail_restricted(request.user)


OWN_MAIL_SUBJECT = "(Sent from the site's own address: shown to staff with the Mail app only)"


def hide_own_mail(messages: list[dict]) -> list[dict]:
    """List rows for a user who may not read Sent mail: a message from the site's own address keeps its row, sender
    and date, but not its subject or opening text (opening it is refused as well)."""
    return [
        {**msg, "subject": OWN_MAIL_SUBJECT, "snippet": ""} if msg.get("from_own_mailbox") else msg for msg in messages
    ]


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
