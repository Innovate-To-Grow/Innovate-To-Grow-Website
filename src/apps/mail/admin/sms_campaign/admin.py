"""Broadcast SMS campaign admin."""

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import escape, format_html
from unfold.decorators import action, display

from apps.core.admin import BaseModelAdmin
from apps.mail.models import SmsCampaign
from apps.mail.models.sms_campaign import SMS_AUDIENCE_CHOICES

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
class SmsCampaignAdmin(SmsCampaignSendViewsMixin, BaseModelAdmin):
    form = SmsCampaignForm
    change_form_template = "admin/mail/smscampaign/change_form.html"
    change_list_template = "admin/mail/smscampaign/change_list.html"
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
    )
    filter_horizontal = ("selected_members", "exclude_members")
    conditional_fields = {
        "event": (
            "audience_type === 'event_registrants' || audience_type === 'ticket_type'"
            " || audience_type === 'checked_in' || audience_type === 'not_checked_in'"
        ),
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

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/preview-recipients/",
                self.admin_site.admin_view(self.preview_recipients_view),
                name="mail_smscampaign_preview_recipients",
            ),
            path(
                "<path:object_id>/send-sms/",
                self.admin_site.admin_view(self.send_sms_preview_view),
                name="mail_smscampaign_send_preview",
            ),
            path(
                "<path:object_id>/send-sms/confirm/",
                self.admin_site.admin_view(self.send_sms_confirm_view),
                name="mail_smscampaign_send_confirm",
            ),
            path(
                "<path:object_id>/send-sms/status/",
                self.admin_site.admin_view(self.send_sms_status_view),
                name="mail_smscampaign_send_status",
            ),
            path(
                "<path:object_id>/send-sms/status.json",
                self.admin_site.admin_view(self.send_sms_status_json),
                name="mail_smscampaign_send_status_json",
            ),
        ]
        return custom_urls + super().get_urls()

    @action(description="Preview SMS", url_path="preview-sms", icon="visibility")
    def preview_sms_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_preview", args=[object_id]))

    @action(description="Preview Recipients", url_path="preview-recipients", icon="group")
    def preview_recipients_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_preview_recipients", args=[object_id]))

    @action(description="Send SMS Campaign", url_path="send-sms", icon="send")
    def send_sms_campaign_action(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        if obj.status != "draft":
            messages.warning(request, "This SMS campaign has already been sent.")
            return HttpResponseRedirect(reverse("admin:mail_smscampaign_change", args=[object_id]))
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_preview", args=[object_id]))

    @display(description="Campaign")
    def name_preview(self, obj):
        return obj.name[:60] + "..." if len(obj.name) > 60 else obj.name

    @display(description="Audience", label=True)
    def audience_badge(self, obj):
        badge_colors = {
            "subscribers": ("Subscribers", "info"),
            "event_registrants": ("Event", "warning"),
            "ticket_type": ("Ticket Type", "warning"),
            "checked_in": ("Checked In", "success"),
            "not_checked_in": ("No-Shows", "danger"),
            "all_members": ("All Members", "info"),
            "staff": ("Staff", "info"),
            "selected_members": ("Selected", "info"),
            "manual": ("Manual", "info"),
        }
        return badge_colors.get(obj.audience_type, (obj.get_audience_type_display(), "info"))

    @display(description="Phone Eligibility", label=True)
    def phone_policy_badge(self, obj):
        if obj.phone_policy == "verified_opt_in":
            return "Verified opt-ins", "success"
        return "Any verified", "warning"

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"draft": "info", "sending": "warning", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="SMS Message")
    def message_readonly(self, obj):
        if not obj:
            return "-"
        return format_html(
            '<pre class="max-h-[70vh] max-w-2xl overflow-auto whitespace-pre-wrap break-words '
            "rounded-default border border-base-200 bg-base-50 px-3 py-2 font-mono text-sm font-medium "
            'text-font-default-light shadow-xs dark:border-base-700 dark:bg-base-800 dark:text-font-default-dark">'
            "{message}</pre>",
            message=escape(obj.message or ""),
        )

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

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            from apps.core.models import AWSCredentialConfig

            extra_context["aws_config"] = AWSCredentialConfig.load()
        except Exception:
            extra_context.setdefault("aws_config", None)
        return super().changelist_view(request, extra_context=extra_context)
