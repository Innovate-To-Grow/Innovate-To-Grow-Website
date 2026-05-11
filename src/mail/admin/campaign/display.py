"""Display and read-only behavior for campaign admin."""

import base64

from django.utils.html import escape, format_html
from unfold.decorators import display

import mail.admin.campaign as campaign_api
from core.models import EmailServiceConfig, GmailImportConfig


class CampaignDisplayMixin:
    @display(description="Subject")
    def subject_preview(self, obj):
        return obj.subject[:60] + "..." if len(obj.subject) > 60 else obj.subject

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

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"draft": "info", "sending": "warning", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="Email Content")
    def body_readonly(self, obj):
        """Read-only full body with Copy HTML for non-draft campaigns."""
        if not obj:
            return "-"
        body = obj.body or ""
        b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
        return format_html(
            '<div class="itg-campaign-body-readonly w-full max-w-3xl">'
            '<div class="mb-2 flex flex-wrap items-center justify-end gap-2">'
            '<button type="button" data-b64="{b64}" class="itg-copy-campaign-body '
            "rounded-default border-2 border-primary-600 bg-white px-3 py-1.5 text-xs font-semibold "
            "text-primary-700 shadow-sm hover:bg-primary-50 focus:outline focus:outline-2 "
            "focus:outline-offset-2 focus:outline-primary-600 dark:border-primary-500 dark:bg-base-900 "
            'dark:text-primary-300 dark:hover:bg-base-800">'
            "Copy HTML</button></div>"
            '<pre class="max-h-[70vh] max-w-2xl overflow-auto whitespace-pre-wrap break-words '
            "rounded-default border border-base-200 bg-base-50 px-3 py-2 font-mono text-sm font-medium "
            "text-font-default-light shadow-xs dark:border-base-700 dark:bg-base-800 dark:text-font-default-dark"
            '">{body_escaped}</pre></div>',
            b64=b64,
            body_escaped=escape(body),
        )

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj and obj.status != "draft":
            for i, (title, options) in enumerate(fieldsets):
                if "fields" not in options:
                    continue
                fields = list(options["fields"])
                if "body" in fields:
                    fields[fields.index("body")] = "body_readonly"
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
                    "subject",
                    "login_redirect_path",
                    "include_unsubscribe_header",
                    "body_readonly",
                    "audience_type",
                    "event",
                    "member_email_scope",
                    "manual_emails",
                    "selected_members",
                    "exclude_audience_type",
                    "exclude_member_email_scope",
                    "exclude_event",
                    "exclude_members",
                ]
            )
        return readonly

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            extra_context["email_config"] = EmailServiceConfig.load()
            extra_context["gmail_import_config"] = GmailImportConfig.load()
            extra_context["gmail_mailbox"] = campaign_api.resolve_gmail_mailbox()
            extra_context["gmail_folder"] = campaign_api.GMAIL_FOLDER_DISPLAY
        except Exception:
            extra_context.setdefault("email_config", None)
            extra_context.setdefault("gmail_import_config", None)
            extra_context.setdefault("gmail_mailbox", "")
            extra_context.setdefault("gmail_folder", campaign_api.GMAIL_FOLDER_DISPLAY)
        return super().changelist_view(request, extra_context=extra_context)
