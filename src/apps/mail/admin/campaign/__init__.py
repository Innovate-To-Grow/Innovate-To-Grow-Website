"""Email campaign admin. View services live in ``campaign.services`` (patch them there)."""

from .admin import EmailCampaignAdmin
from .forms import EmailCampaignForm
from .inlines import AudienceTypeFilter, RecipientLogInline
from .services import (
    GMAIL_FOLDER_DISPLAY,
    GmailImportError,
    get_recipients,
    import_message_into_campaign,
    list_recent_sent_messages,
    render_preview,
    resolve_gmail_mailbox,
)
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
]
