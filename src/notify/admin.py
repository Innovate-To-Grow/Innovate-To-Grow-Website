from django.contrib import admin

from .models import NotificationLog, VerificationRequest


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "channel",
        "method",
        "target",
        "purpose",
        "status",
        "expires_at",
        "attempts",
        "created_at",
    )
    list_filter = ("channel", "method", "status", "purpose", "created_at")
    search_fields = ("target", "code", "token", "purpose")
    readonly_fields = ("created_at", "updated_at", "verified_at")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "channel",
        "target",
        "provider",
        "status",
        "sent_at",
        "created_at",
    )
    list_filter = ("channel", "status", "provider", "created_at")
    search_fields = ("target", "subject")
    readonly_fields = ("created_at", "updated_at", "sent_at")
