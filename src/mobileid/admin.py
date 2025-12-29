"""
Admin registrations for Mobile ID domain.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Barcode, MobileID, Transaction


@admin.register(Barcode)
class BarcodeAdmin(admin.ModelAdmin):
    """Admin for Barcode model."""

    list_display = ("model_user", "barcode_type", "barcode", "barcode_uuid", "has_profile", "time_created")
    list_filter = ("barcode_type", "time_created")
    search_fields = ("model_user__username", "barcode", "barcode_uuid", "profile_name")
    readonly_fields = ("barcode_uuid", "time_created")
    autocomplete_fields = ["model_user"]

    fieldsets = (
        (None, {"fields": ("model_user", "barcode_type", "barcode")}),
        (_("Profile"), {"fields": ("profile_name", "profile_information_id", "profile_img"), "classes": ("collapse",)}),
        (_("Metadata"), {"fields": ("barcode_uuid", "time_created"), "classes": ("collapse",)}),
    )

    @admin.display(description="Has Profile", boolean=True)
    def has_profile(self, obj):
        return obj.has_profile


@admin.register(MobileID)
class MobileIDAdmin(admin.ModelAdmin):
    """Admin for MobileID model."""

    list_display = ("model_user", "user_barcode", "user_mobile_id_server")
    list_filter = ("user_mobile_id_server",)
    search_fields = ("model_user__username", "user_barcode__barcode")
    autocomplete_fields = ["model_user", "user_barcode"]

    fieldsets = ((None, {"fields": ("model_user", "user_barcode", "user_mobile_id_server")}),)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin for Transaction model - read-only transaction log."""

    list_display = ("model_user", "barcode_used", "time_used")
    list_filter = ("time_used", "barcode_used__barcode_type")
    search_fields = ("model_user__username", "barcode_used__barcode")
    readonly_fields = ("model_user", "barcode_used", "time_used")
    date_hierarchy = "time_used"

    # Make this admin mostly read-only for transaction logging
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

