"""
Barcode model admin configuration.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import Barcode


@admin.register(Barcode)
class BarcodeAdmin(ModelAdmin):
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
