"""Email campaign model admin."""

from django.contrib import admin

from core.admin import BaseModelAdmin
from mail.models import EmailCampaign

from .display import CampaignDisplayMixin
from .forms import EmailCampaignForm
from .inlines import AudienceTypeFilter
from .views import (
    CampaignGmailMixin,
    CampaignPreviewMixin,
    CampaignSendMixin,
    CampaignStatusMixin,
    CampaignUrlsMixin,
)


@admin.register(EmailCampaign)
class EmailCampaignAdmin(
    CampaignUrlsMixin,
    CampaignPreviewMixin,
    CampaignGmailMixin,
    CampaignSendMixin,
    CampaignStatusMixin,
    CampaignDisplayMixin,
    BaseModelAdmin,
):
    form = EmailCampaignForm
    change_form_template = "admin/mail/emailcampaign/change_form.html"

    class Media:
        js = ("mail/js/body_format_toggle.js", "mail/js/body_html_editor.js")

    list_display = (
        "subject_preview",
        "audience_badge",
        "status_badge",
        "sent_count",
        "failed_count",
        "sent_at",
    )
    list_filter = ("status", AudienceTypeFilter)
    search_fields = ("subject",)
    ordering = ("-created_at",)
    actions_detail = [
        "preview_email_action",
        "preview_recipients_action",
        "import_gmail_html_action",
        "send_campaign_action",
    ]

    fieldsets = (
        (
            "Audience",
            {
                "fields": (
                    "audience_type",
                    "event",
                    "ticket",
                    "selected_members",
                    "member_email_scope",
                    "manual_emails",
                    "exclude_audience_type",
                    "exclude_member_email_scope",
                    "exclude_event",
                    "exclude_ticket",
                    "exclude_members",
                ),
            },
        ),
        (
            "Campaign",
            {"fields": ("subject", "login_redirect_path", "include_unsubscribe_header", "body_format", "body")},
        ),
    )
    filter_horizontal = ("selected_members", "exclude_members")
    conditional_fields = {
        "event": (
            "audience_type === 'event_registrants' || audience_type === 'ticket_type'"
            " || audience_type === 'checked_in' || audience_type === 'not_checked_in'"
        ),
        "ticket": "audience_type === 'ticket_type'",
        "selected_members": "audience_type === 'selected_members'",
        "member_email_scope": (
            "audience_type === 'subscribers' || audience_type === 'all_members'"
            " || audience_type === 'staff' || audience_type === 'selected_members'"
        ),
        "manual_emails": "audience_type === 'manual'",
        "exclude_event": (
            "exclude_audience_type === 'event_registrants' || exclude_audience_type === 'ticket_type'"
            " || exclude_audience_type === 'checked_in' || exclude_audience_type === 'not_checked_in'"
        ),
        "exclude_ticket": "exclude_audience_type === 'ticket_type'",
        "exclude_members": "exclude_audience_type === 'selected_members'",
        "exclude_member_email_scope": (
            "exclude_audience_type === 'subscribers' || exclude_audience_type === 'all_members'"
            " || exclude_audience_type === 'staff' || exclude_audience_type === 'selected_members'"
        ),
    }
