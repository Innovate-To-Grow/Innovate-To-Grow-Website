from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import BaseModelAdmin

from ....models import ContactEmail


@admin.register(ContactEmail)
class ContactEmailAdmin(BaseModelAdmin):
    """Admin for ContactEmail model."""

    list_display = (
        "email_address",
        "member",
        "email_type",
        "verified",
        "subscribe",
        "created_at",
    )
    list_filter = ("email_type", "verified", "subscribe", "created_at")
    search_fields = ("email_address", "member__first_name", "member__last_name")
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("verified", "subscribe")
    autocomplete_fields = ["member"]
    fieldsets = (
        (None, {"fields": ("member", "email_address", "email_type")}),
        (_("Status"), {"fields": ("verified", "subscribe")}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    actions = ["mark_verified", "mark_unverified", "toggle_subscribe"]

    @admin.action(description="Mark selected emails as verified")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} email(s) marked as verified.")

    @admin.action(description="Mark selected emails as unverified")
    def mark_unverified(self, request, queryset):
        updated = queryset.update(verified=False)
        self.message_user(request, f"{updated} email(s) marked as unverified.")

    @admin.action(description="Toggle subscription status")
    def toggle_subscribe(self, request, queryset):
        for email in queryset:
            email.subscribe = not email.subscribe
            email.save()
        self.message_user(
            request,
            f"Toggled subscription for {queryset.count()} email(s).",
        )
