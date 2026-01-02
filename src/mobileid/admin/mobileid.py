from django.contrib import admin

from ..models.mobileid import MobileID


@admin.register(MobileID)
class MobileIDAdmin(admin.ModelAdmin):
    """Admin for MobileID model."""

    list_display = ("model_user", "user_barcode", "user_mobile_id_server")
    list_filter = ("user_mobile_id_server",)
    search_fields = ("model_user__username", "user_barcode__barcode")
    autocomplete_fields = ["model_user", "user_barcode"]

    fieldsets = ((None, {"fields": ("model_user", "user_barcode", "user_mobile_id_server")}),)

