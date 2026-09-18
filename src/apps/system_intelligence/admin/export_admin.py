from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.admin.common.base import BaseModelAdmin
from apps.system_intelligence.models import SystemIntelligenceExport


def _can_download(export, user):
    """Mirror the download view's authorization so the admin only links what will open."""
    return bool(export.file) and (export.created_by_id == user.pk or user.is_superuser)


def _download_anchor(export):
    url = reverse("admin:system_intelligence_export_download", args=[export.pk])
    return format_html('<a href="{}" download>{}</a>', url, export.filename)


@admin.register(SystemIntelligenceExport)
class SystemIntelligenceExportAdmin(BaseModelAdmin):
    """Browse and prune the Excel files the assistant generated for admins.

    Records are created only by the ``export_*_to_excel`` tools, so the admin is
    read-only apart from delete; deleting a record also removes its file from
    storage via the ``post_delete`` signal.
    """

    list_display = ("title", "model_label", "row_count", "created_by", "created_at")
    list_filter = ("model_label", "created_at")
    list_select_related = ("created_by", "conversation")
    search_fields = ("title", "filename", "model_label", "created_by__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "title",
        "filename",
        "download_link",
        "model_label",
        "field_names_display",
        "row_count",
        "conversation",
        "created_by",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("id", "title", "filename", "download_link")}),
        (_("Contents"), {"fields": ("model_label", "field_names_display", "row_count")}),
        (_("Origin"), {"fields": ("conversation", "created_by")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def get_list_display(self, request):
        # The download view authorizes per user, so build the column per request
        # and only render a link where the click will succeed.
        user = request.user

        @admin.display(description=_("File"))
        def file_column(obj):
            return _download_anchor(obj) if _can_download(obj, user) else obj.filename

        return (*self.list_display, file_column)

    @admin.display(description=_("Download"))
    def download_link(self, obj):
        if not obj.file:
            return _("File is missing on storage.")
        return _download_anchor(obj)

    @admin.display(description=_("Columns"))
    def field_names_display(self, obj):
        return ", ".join(obj.field_names or []) or "—"
