"""
Security-related admin configuration.
Includes RSA Keypair management.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from ..models import RSAKeypair


@admin.register(RSAKeypair)
class RSAKeypairAdmin(ModelAdmin):
    """Admin for RSAKeypair model - security settings."""

    list_display = ("name", "key_id", "is_active", "created_at", "rotated_at")
    list_filter = ("is_active", "created_at", "rotated_at")
    search_fields = ("name", "key_id")

    def get_readonly_fields(self, request, obj=None):
        """Keys are read-only after creation (auto-generated)."""
        if obj:  # Editing existing object
            return ("key_id", "public_key_pem", "private_key_pem", "created_at", "rotated_at")
        return ("key_id",)

    def get_fieldsets(self, request, obj=None):
        """Show different fieldsets for add vs change."""
        if obj:  # Editing existing object - show keys as read-only
            return (
                (None, {"fields": ("name", "key_id", "is_active")}),
                (
                    _("Keys (Auto-generated, Read-only)"),
                    {
                        "fields": ("public_key_pem", "private_key_pem"),
                        "classes": ("collapse",),
                        "description": "RSA keys in PEM format. These are auto-generated and cannot be modified.",
                    },
                ),
                (_("Timestamps"), {"fields": ("created_at", "rotated_at"), "classes": ("collapse",)}),
            )
        else:  # Adding new object - only show name and is_active
            return (
                (
                    None,
                    {"fields": ("name", "is_active"), "description": "RSA keys will be auto-generated when you save."},
                ),
            )

    # Actions
    actions = ["deactivate_keypairs", "activate_keypairs", "regenerate_keys"]

    @admin.action(description="Deactivate selected keypairs")
    def deactivate_keypairs(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} keypair(s) deactivated.")

    @admin.action(description="Activate selected keypairs")
    def activate_keypairs(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} keypair(s) activated.")

    @admin.action(description="Regenerate keys for selected keypairs")
    def regenerate_keys(self, request, queryset):
        for keypair in queryset:
            public_pem, private_pem = RSAKeypair.generate_keypair()
            keypair.rotate(public_pem, private_pem)
        self.message_user(request, f"{queryset.count()} keypair(s) regenerated.")
