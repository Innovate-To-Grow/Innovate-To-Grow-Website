"""Services the campaign admin views use; tests patch names here."""

from apps.mail.services.audience import get_recipients
from apps.mail.services.campaign.content.personalize import recipients_without_login_link
from apps.mail.services.campaign.content.preview import render_preview
from apps.mail.services.campaign.gmail_import import (
    GMAIL_FOLDER_DISPLAY,
    GmailImportError,
    import_message_into_campaign,
    list_recent_sent_messages,
    resolve_gmail_mailbox,
)

__all__ = [
    "GMAIL_FOLDER_DISPLAY",
    "GmailImportError",
    "get_recipients",
    "import_message_into_campaign",
    "list_recent_sent_messages",
    "recipients_without_login_link",
    "render_preview",
    "resolve_gmail_mailbox",
]
