from django.contrib import admin

from apps.core.admin import BaseModelAdmin
from apps.core.admin.utils import format_json

from ..models import PastProjectShare


@admin.register(PastProjectShare)
class PastProjectShareAdmin(BaseModelAdmin):
    """View + delete only. Shares are user-generated snapshots — staff never hand-edit them."""

    list_display = ("name", "created_by", "row_count", "created_at")
    list_filter = ("created_at",)
    search_fields = (
        "name",
        "note",
        "details_text",
        "created_by__first_name",
        "created_by__last_name",
        "created_by__contact_emails__email_address",
    )
    readonly_fields = ("id", "name", "note", "details_text", "created_by", "rows_preview", "created_at", "updated_at")

    fieldsets = (
        ("Share", {"fields": ("id", "name", "note", "details_text", "created_by")}),
        ("Rows", {"fields": ("rows_preview",)}),
        ("System", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Read-only detail view; staff may still delete (BaseModelAdmin.has_delete_permission).
        return False

    @admin.display(description="Rows")
    def row_count(self, obj):
        return len(obj.rows or [])

    @admin.display(description="Rows (JSON)")
    def rows_preview(self, obj):
        return format_json(obj.rows)
