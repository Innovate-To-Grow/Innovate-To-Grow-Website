from django.contrib import admin

from ..models.transaction import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin for Transaction model - read-only transaction log."""

    list_display = ("model_user", "barcode_used", "created_at")
    list_filter = ("created_at", "barcode_used__barcode_type")
    search_fields = ("model_user__username", "barcode_used__barcode")
    readonly_fields = ("model_user", "barcode_used", "created_at")
    date_hierarchy = "created_at"

    # Make this admin mostly read-only for transaction logging
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
