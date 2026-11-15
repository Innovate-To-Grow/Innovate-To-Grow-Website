"""Email campaign admin. View services live in ``campaign.views.services`` (patch them there)."""

from .admin import EmailCampaignAdmin
from .admin.inlines import AudienceTypeFilter, RecipientLogInline
from .forms import EmailCampaignForm
from .forms.widgets import BODY_FORMAT_CHOICES, ManualEmailsWidget, PersonalizationTextInput, TicketSelectWidget
from .views.services import (
    GMAIL_FOLDER_DISPLAY,
    GmailImportError,
    get_recipients,
    import_message_into_campaign,
    list_recent_sent_messages,
    render_preview,
    resolve_gmail_mailbox,
)

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
