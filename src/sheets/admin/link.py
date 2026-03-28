from django.contrib import admin
from django.urls import path
from unfold.admin import ModelAdmin

from sheets.admin.link_helpers import (
    SHEETLINK_FIELDSETS,
    build_editor_context,
    get_content_type_queryset,
    get_model_fields_response,
    handle_sync_view,
    run_bulk_sync,
)
from sheets.models import SheetLink


@admin.register(SheetLink)
class SheetLinkAdmin(ModelAdmin):
    add_form_template = "admin/sheets/sheetlink/change_form.html"
    change_form_template = "admin/sheets/sheetlink/change_form.html"
    list_display = ("name", "content_type", "spreadsheet_id_short", "sync_direction", "is_active", "last_sync_status")
    list_filter = ("sync_direction", "is_active", "content_type")
    search_fields = ("name", "spreadsheet_id")
    readonly_fields = ("id", "created_at", "updated_at")
    actions = ["pull_selected", "push_selected"]

    fieldsets = SHEETLINK_FIELDSETS

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "content_type":
            kwargs["queryset"] = get_content_type_queryset()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Sheet ID")
    def spreadsheet_id_short(self, obj):
        sid = obj.spreadsheet_id
        if len(sid) > 20:
            return f"{sid[:10]}...{sid[-6:]}"
        return sid

    @admin.display(description="Last Sync")
    def last_sync_status(self, obj):
        last_log = obj.sync_logs.order_by("-started_at").first()
        if not last_log:
            return "—"
        return (
            f"{last_log.get_direction_display()} {last_log.get_status_display()} ({last_log.started_at:%Y-%m-%d %H:%M})"
        )

    # ------------------------------------------------------------------
    # Column mapping visual editor context
    # ------------------------------------------------------------------

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id) if object_id else None
        extra_context.update(build_editor_context(obj))
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(build_editor_context())
        return super().add_view(request, form_url, extra_context)

    # ------------------------------------------------------------------
    # AJAX endpoint: model fields for a content type
    # ------------------------------------------------------------------

    def model_fields_view(self, request, content_type_id):
        return get_model_fields_response(content_type_id)

    # ------------------------------------------------------------------
    # Custom URLs for pull/push
    # ------------------------------------------------------------------

    def get_urls(self):
        custom_urls = [
            path(
                "model-fields/<int:content_type_id>/",
                self.admin_site.admin_view(self.model_fields_view),
                name="sheets_sheetlink_model_fields",
            ),
            path(
                "<path:object_id>/pull/",
                self.admin_site.admin_view(self.pull_view),
                name="sheets_sheetlink_pull",
            ),
            path(
                "<path:object_id>/push/",
                self.admin_site.admin_view(self.push_view),
                name="sheets_sheetlink_push",
            ),
        ]
        return custom_urls + super().get_urls()

    def pull_view(self, request, object_id):
        return handle_sync_view(self, request, object_id, "pull")

    def push_view(self, request, object_id):
        return handle_sync_view(self, request, object_id, "push")

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------

    @admin.action(description="Pull selected links (Sheet → DB)")
    def pull_selected(self, request, queryset):
        from sheets.services.sync import pull_from_sheet

        run_bulk_sync(request, queryset, pull_from_sheet)

    @admin.action(description="Push selected links (DB → Sheet)")
    def push_selected(self, request, queryset):
        from sheets.services.sync import push_to_sheet

        run_bulk_sync(request, queryset, push_to_sheet)
