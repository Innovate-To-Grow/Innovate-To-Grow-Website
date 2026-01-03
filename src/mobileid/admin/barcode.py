from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ..models.barcode import Barcode


@admin.register(Barcode)
class BarcodeAdmin(admin.ModelAdmin):
    """Admin for Barcode model."""

    list_display = ("model_user", "barcode_type", "barcode", "barcode_uuid", "has_profile", "created_at")
    list_filter = ("barcode_type", "created_at")
    search_fields = ("model_user__username", "barcode", "barcode_uuid", "profile_name")
    readonly_fields = ("barcode_uuid", "created_at")
    autocomplete_fields = ["model_user"]

    fieldsets = (
        (None, {"fields": ("model_user", "barcode_type", "barcode")}),
        (_("Profile"), {"fields": ("profile_name", "profile_information_id", "profile_img"), "classes": ("collapse",)}),
        (_("Metadata"), {"fields": ("barcode_uuid", "created_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Has Profile", boolean=True)
    def has_profile(self, obj):
        return obj.has_profile
