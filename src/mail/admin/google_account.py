"""
Admin configuration for GoogleAccount with custom inbox and compose flows.
"""

from django.contrib import admin
from django.urls import path

from core.admin.base import BaseModelAdmin
from mail.forms import GoogleAccountForm
from mail.models import GoogleAccount
from mail.services.gmail import GmailService, GmailServiceError

from .google.actions import set_as_active, test_connection
from .google.views import (
    compose_view,
    message_detail_view,
    message_operation_view,
    render_mailbox_view,
    reply_or_forward_view,
    send_action,
)


@admin.register(GoogleAccount)
class GoogleAccountAdmin(BaseModelAdmin):
    """Admin for Gmail API accounts with inbox, detail, and compose tooling."""

    form = GoogleAccountForm
    list_display = ("email", "display_name", "is_active_badge", "last_used_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("email", "display_name")
    readonly_fields = ("id", "last_used_at", "last_error", "created_at", "updated_at")
    actions = ["test_connection", "set_as_active"]
    fieldsets = (
        (None, {"fields": ("email", "display_name", "is_active")}),
        (
            "Credentials",
            {
                "fields": ("service_account_json",),
                "classes": ("collapse",),
                "description": "Service account JSON key from Google Cloud Console.",
            },
        ),
        ("Operational Info", {"fields": ("last_used_at", "last_error"), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("id", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Active", boolean=True, ordering="is_active")
    def is_active_badge(self, obj):
        return obj.is_active

    @admin.action(description="Test Gmail API connection for selected accounts")
    def test_connection(self, request, queryset):
        test_connection(self, request, queryset, GmailService, GmailServiceError)

    @admin.action(description="Set selected account as active")
    def set_as_active(self, request, queryset):
        set_as_active(self, request, queryset)

    def get_urls(self):
        custom_urls = [
            path("inbox/", self.admin_site.admin_view(self.inbox_view), name="mail_inbox"),
            path(
                "inbox/<str:message_id>/",
                self.admin_site.admin_view(self.message_detail_view),
                name="mail_message_detail",
            ),
            path("compose/", self.admin_site.admin_view(self.compose_view), name="mail_compose"),
            path("reply/<str:message_id>/", self.admin_site.admin_view(self.reply_view), name="mail_reply"),
            path("forward/<str:message_id>/", self.admin_site.admin_view(self.forward_view), name="mail_forward"),
            path("sent/", self.admin_site.admin_view(self.sent_view), name="mail_sent"),
            path("send/", self.admin_site.admin_view(self.send_action), name="mail_send"),
            path("trash/<str:message_id>/", self.admin_site.admin_view(self.trash_action), name="mail_trash"),
            path("labels/<str:message_id>/", self.admin_site.admin_view(self.labels_action), name="mail_labels"),
            path(
                "attachment/<str:message_id>/<str:attachment_id>/",
                self.admin_site.admin_view(self.attachment_view),
                name="mail_attachment",
            ),
        ]
        return custom_urls + super().get_urls()

    def inbox_view(self, request):
        return render_mailbox_view(
            self, request, GmailService, GmailServiceError, label_ids=["INBOX"], title="Inbox", current_view="inbox"
        )

    def sent_view(self, request):
        return render_mailbox_view(
            self, request, GmailService, GmailServiceError, label_ids=["SENT"], title="Sent Mail", current_view="sent"
        )

    def message_detail_view(self, request, message_id):
        return message_detail_view(self, request, message_id, GmailService, GmailServiceError)

    def compose_view(self, request):
        return compose_view(self, request, GmailService)

    def reply_view(self, request, message_id):
        return reply_or_forward_view(self, request, message_id, GmailService, GmailServiceError, mode="reply")

    def forward_view(self, request, message_id):
        return reply_or_forward_view(self, request, message_id, GmailService, GmailServiceError, mode="forward")

    def send_action(self, request):
        return send_action(self, request, GmailService, GmailServiceError)

    def trash_action(self, request, message_id):
        return message_operation_view(self, request, message_id, GmailService, GmailServiceError, op="trash")

    def labels_action(self, request, message_id):
        return message_operation_view(self, request, message_id, GmailService, GmailServiceError, op="labels")

    def attachment_view(self, request, message_id, attachment_id):
        return message_operation_view(self, request, message_id, GmailService, GmailServiceError, op="attachment")
