"""
Contact information admin configuration.
Includes ContactEmail and ContactPhone.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from ...models import ContactEmail, ContactPhone

# ============================================================================
# Contact Email Admin
# ============================================================================


@admin.register(ContactEmail)
class ContactEmailAdmin(ModelAdmin):
    """Admin for ContactEmail model."""

    list_display = ("email_address", "member", "email_type", "verified", "subscribe", "created_at")
    list_filter = ("email_type", "verified", "subscribe", "created_at")
    search_fields = ("email_address", "member__username", "member__email")
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("verified", "subscribe")
    autocomplete_fields = ["member"]

    fieldsets = (
        (None, {"fields": ("member", "email_address", "email_type")}),
        (_("Status"), {"fields": ("verified", "subscribe")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    # Actions
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
        self.message_user(request, f"Toggled subscription for {queryset.count()} email(s).")


# ============================================================================
# Contact Phone Admin
# ============================================================================


@admin.register(ContactPhone)
class ContactPhoneAdmin(ModelAdmin):
    """Admin for ContactPhone model."""

    list_display = ("phone_number", "member", "region", "get_formatted_number", "subscribe", "created_at")
    list_filter = ("region", "subscribe", "created_at")
    search_fields = ("phone_number", "member__username", "member__email")
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("subscribe",)
    autocomplete_fields = ["member"]

    fieldsets = (
        (None, {"fields": ("member", "phone_number", "region")}),
        (_("Status"), {"fields": ("subscribe",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Formatted Number")
    def get_formatted_number(self, obj):
        return obj.get_formatted_number()
