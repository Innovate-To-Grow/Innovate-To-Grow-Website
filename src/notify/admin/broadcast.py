from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from ..models import BroadcastMessage
from ..services import send_broadcast_message


@admin.register(BroadcastMessage)
class BroadcastMessageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "channel",
        "scope",
        "status",
        "total_recipients",
        "sent_count",
        "failed_count",
        "sent_at",
        "updated_at",
    )
    list_filter = ("channel", "scope", "status", "created_at")
    search_fields = ("name", "subject", "message")
    readonly_fields = (
        "status",
        "total_recipients",
        "sent_count",
        "failed_count",
        "last_error",
        "sent_at",
        "created_at",
        "updated_at",
    )
    actions = ["send_broadcast"]
    fieldsets = (
        (
            _("Content"),
            {
                "fields": (
                    "name",
                    "channel",
                    "scope",
                    "subject",
                    "message",
                )
            },
        ),
        (
            _("Delivery status"),
            {
                "fields": (
                    "status",
                    "total_recipients",
                    "sent_count",
                    "failed_count",
                    "last_error",
                    "sent_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.action(description=_("Send selected broadcasts to subscribers"))
    def send_broadcast(self, request, queryset):
        sent = 0
        skipped = 0
        errors = 0

        for broadcast in queryset:
            if not broadcast.is_sendable:
                skipped += 1
                continue

            try:
                send_broadcast_message(broadcast)
                sent += 1
            except Exception as exc:  # pragma: no cover - defensive logging
                errors += 1
                self.message_user(
                    request,
                    _(f"Failed to send '{broadcast}': {exc}"),
                    level=messages.ERROR,
                )

        if sent:
            self.message_user(
                request,
                _(f"Successfully started {sent} broadcast(s)."),
                level=messages.SUCCESS,
            )

        if skipped:
            self.message_user(
                request,
                _(f"Skipped {skipped} broadcast(s) already sent."),
                level=messages.WARNING,
            )

        if not sent and not skipped and errors == 0:
            self.message_user(
                request,
                _("No broadcasts were sent."),
                level=messages.INFO,
            )
