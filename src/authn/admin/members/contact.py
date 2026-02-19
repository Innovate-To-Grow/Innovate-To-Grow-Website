"""
Contact information admin configuration.
Includes ContactEmail, ContactPhone, and MemberContactInfo.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from ...models import ContactEmail, ContactPhone, MemberContactInfo

# ============================================================================
# Contact Email Admin
# ============================================================================


@admin.register(ContactEmail)
class ContactEmailAdmin(ModelAdmin):
    """Admin for ContactEmail model."""

    list_display = ("email_address", "email_type", "verified", "subscribe", "created_at")
    list_filter = ("email_type", "verified", "subscribe", "created_at")
    search_fields = ("email_address",)
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("verified", "subscribe")

    fieldsets = (
        (None, {"fields": ("email_address", "email_type")}),
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

    list_display = ("phone_number", "region", "get_formatted_number", "subscribe", "created_at")
    list_filter = ("region", "subscribe", "created_at")
    search_fields = ("phone_number",)
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("subscribe",)

    fieldsets = (
        (None, {"fields": ("phone_number", "region")}),
        (_("Status"), {"fields": ("subscribe",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Formatted Number")
    def get_formatted_number(self, obj):
        return obj.get_formatted_number()


# ============================================================================
# Member Contact Info Admin
# ============================================================================


@admin.register(MemberContactInfo)
class MemberContactInfoAdmin(ModelAdmin):
    """Admin for MemberContactInfo model."""

    list_display = ("model_user", "contact_email", "contact_phone", "is_email_verified", "created_at")
    list_filter = ("created_at", "contact_email__verified")
    search_fields = (
        "model_user__username",
        "model_user__email",
        "contact_email__email_address",
        "contact_phone__phone_number",
    )
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ["model_user", "contact_email", "contact_phone"]

    fieldsets = (
        (None, {"fields": ("model_user",)}),
        (_("Contact Details"), {"fields": ("contact_email", "contact_phone")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
