"""Email campaign admin package with patch-compatible service aliases."""

import threading

from mail.services.audience import get_recipients
from mail.services.gmail_import import (
    GMAIL_FOLDER_DISPLAY,
    GmailImportError,
    import_message_into_campaign,
    list_recent_sent_messages,
    resolve_gmail_mailbox,
)
from mail.services.preview import render_preview

from .admin import EmailCampaignAdmin
from .forms import EmailCampaignForm
from .inlines import AudienceTypeFilter, RecipientLogInline
from .widgets import BODY_FORMAT_CHOICES, ManualEmailsWidget, PersonalizationTextInput, TicketSelectWidget

__all__ = [
    "AudienceTypeFilter",
    "BODY_FORMAT_CHOICES",
    "EmailCampaignAdmin",
    "EmailCampaignForm",
    "GMAIL_FOLDER_DISPLAY",
    "GmailImportError",
    "ManualEmailsWidget",
    "PersonalizationTextInput",
    "RecipientLogInline",
    "TicketSelectWidget",
    "get_recipients",
    "import_message_into_campaign",
    "list_recent_sent_messages",
    "render_preview",
    "resolve_gmail_mailbox",
    "threading",
]
