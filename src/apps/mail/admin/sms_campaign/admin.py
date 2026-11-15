"""Broadcast SMS campaign admin."""

from django.contrib import admin

from apps.core.admin import BaseModelAdmin
from apps.mail.models import SmsCampaign
from apps.mail.models.sms.campaign_options import SMS_AUDIENCE_CHOICES

from .actions import SmsCampaignActionsMixin
from .display import SmsCampaignDisplayMixin
from .forms import SmsCampaignForm
from .recipient_logs import SmsRecipientLogInline
from .views import SmsCampaignSendViewsMixin


class SmsAudienceTypeFilter(admin.SimpleListFilter):
    title = "audience type"
    parameter_name = "audience_type"

    def lookups(self, request, model_admin):
        return SMS_AUDIENCE_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(audience_type=self.value())
        return queryset


@admin.register(SmsCampaign)
class SmsCampaignAdmin(SmsCampaignActionsMixin, SmsCampaignDisplayMixin, SmsCampaignSendViewsMixin, BaseModelAdmin):
    form = SmsCampaignForm
    change_form_template = "admin/mail/sms/campaign/change_form.html"
    change_list_template = "admin/mail/sms/campaign/change_list.html"
    inlines = (SmsRecipientLogInline,)

    list_display = (
        "name_preview",
        "audience_badge",
        "phone_policy_badge",
        "status_badge",
        "sent_count",
        "failed_count",
        "sent_at",
    )
    list_filter = ("status", "phone_policy", SmsAudienceTypeFilter)
    search_fields = ("name", "message")
    ordering = ("-created_at",)
    actions = ["resume_paused_recipients_action"]
    actions_detail = [
        "preview_sms_action",
        "preview_recipients_action",
        "send_sms_campaign_action",
    ]

    fieldsets = (
        (
            "Audience",
            {
                "fields": (
                    "phone_policy",
                    "audience_type",
                    "event",
                    "ticket",
                    "ticket_id",
                    "selected_members",
                    "manual_phones",
                    "exclude_audience_type",
                    "exclude_event",
                    "exclude_ticket",
                    "exclude_ticket_id",
                    "exclude_members",
                ),
            },
        ),
        ("Campaign", {"fields": ("name", "message")}),
        (
            "Links",
            {
                "fields": ("login_redirect_path", "link_validity_days"),
                "description": "For {{login_link}}, {{ticket_link}} and {{event_link}}, while links in SMS are allowed "
                "(SMS Settings).",
            },
        ),
    )
    filter_horizontal = ("selected_members", "exclude_members")
    # The event stays visible for every audience: {{event_link}} and {{ticket_link}} open it.
    conditional_fields = {
        "ticket": "audience_type === 'ticket_type'",
        "selected_members": "audience_type === 'selected_members'",
        "manual_phones": "audience_type === 'manual'",
        "exclude_event": (
            "exclude_audience_type === 'event_registrants' || exclude_audience_type === 'ticket_type'"
            " || exclude_audience_type === 'checked_in' || exclude_audience_type === 'not_checked_in'"
        ),
        "exclude_ticket": "exclude_audience_type === 'ticket_type'",
        "exclude_members": "exclude_audience_type === 'selected_members'",
    }

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj and obj.status != "draft":
            for i, (title, options) in enumerate(fieldsets):
                fields = list(options.get("fields", ()))
                if "message" in fields:
                    fields[fields.index("message")] = "message_readonly"
                    fieldsets[i] = (title, {**options, "fields": tuple(fields)})
        if obj and obj.error_message:
            fieldsets.append(("Error Details", {"fields": ("error_message",), "classes": ("collapse",)}))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.error_message:
            readonly.append("error_message")
        if obj and obj.status != "draft":
            readonly.extend(
                [
                    "name",
                    "message_readonly",
                    "login_redirect_path",
                    "link_validity_days",
                    "phone_policy",
                    "audience_type",
                    "event",
                    "ticket_id",
                    "selected_members",
                    "manual_phones",
                    "exclude_audience_type",
                    "exclude_event",
                    "exclude_ticket_id",
                    "exclude_members",
                ]
            )
        return readonly

    def render_change_form(self, request, context, *args, **kwargs):
        from apps.mail.services.sms.content.estimate import composer_settings

        context["sms_composer"] = composer_settings()
        return super().render_change_form(request, context, *args, **kwargs)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            from apps.core.models import AWSCredentialConfig

            extra_context["aws_config"] = AWSCredentialConfig.load()
        except Exception:
            extra_context.setdefault("aws_config", None)
        return super().changelist_view(request, extra_context=extra_context)
