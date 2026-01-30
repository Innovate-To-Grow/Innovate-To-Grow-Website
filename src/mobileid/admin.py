"""
MobileID admin configuration.
"""

from django.contrib import admin

from .models import Barcode, MobileID, Transaction


@admin.register(Barcode)
class BarcodeAdmin(admin.ModelAdmin):
    """Admin for Barcode model."""

    list_display = ("barcode", "barcode_type", "model_user", "profile_name", "created_at")
    list_filter = ("barcode_type", "created_at")
    search_fields = ("barcode", "model_user__username", "model_user__email", "profile_name")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["model_user"]

    fieldsets = (
        (None, {"fields": ("model_user", "barcode_type", "barcode")}),
        ("Profile", {"fields": ("profile_name", "profile_img", "profile_information_id")}),
        ("Metadata", {"fields": ("id", "created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(MobileID)
class MobileIDAdmin(admin.ModelAdmin):
    """Admin for MobileID model."""

    list_display = ("model_user", "user_barcode", "created_at")
    list_filter = ("created_at",)
    search_fields = ("model_user__username", "model_user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["model_user", "user_barcode"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin for Transaction model."""

    list_display = ("id", "created_at")
    readonly_fields = ("id", "created_at", "updated_at")
