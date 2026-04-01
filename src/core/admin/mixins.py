"""Admin mixins for soft-delete, versioning, timestamps, and export formats."""

import json
from datetime import datetime

from django.contrib import admin, messages
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html

# ---------------------------------------------------------------------------
# Core mixins
# ---------------------------------------------------------------------------


class SoftDeleteAdminMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.model.all_objects.all() if hasattr(self.model, "all_objects") else qs

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if hasattr(self.model, "is_deleted") and "deletion_status" not in list_display:
            list_display.append("deletion_status")
        return list_display

    @admin.display(description="Status", boolean=False)
    def deletion_status(self, obj):
        if not hasattr(obj, "is_deleted"):
            return "-"
        if obj.is_deleted:
            return format_html('<span style="color: red;">✗ Deleted</span>')
        return format_html('<span style="color: green;">✓ Active</span>')

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if hasattr(self.model, "is_deleted"):
            filters.insert(0, "is_deleted")
        return filters

    @admin.action(description="Restore selected items")
    def restore_selected(self, request, queryset):
        restored = 0
        for obj in queryset:
            if hasattr(obj, "restore") and obj.is_deleted:
                obj.restore()
                restored += 1
        if restored:
            messages.success(request, f"Successfully restored {restored} item(s).")
            return
        messages.warning(request, "No items were restored.")

    @admin.action(description="Soft delete selected items")
    def soft_delete_selected(self, request, queryset):
        deleted = 0
        for obj in queryset:
            if not obj.is_deleted:
                obj.delete()
                deleted += 1
        if deleted:
            messages.success(request, f"Successfully soft deleted {deleted} item(s).")
            return
        messages.warning(request, "No items were deleted.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if hasattr(self.model, "is_deleted"):
            actions["restore_selected"] = (self.restore_selected, "restore_selected", "Restore selected items")
            actions["soft_delete_selected"] = (
                self.soft_delete_selected,
                "soft_delete_selected",
                "Soft delete selected items",
            )
        return actions


class VersionControlAdminMixin:
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if hasattr(obj, "save_version") and change:
            obj.save_version(comment=f"Updated via admin by {request.user.username}", user=request.user)

    @admin.display(description="Versions")
    def version_count(self, obj):
        if not hasattr(obj, "get_versions"):
            return "-"
        versions = obj.get_versions()
        count = versions.count() if versions else 0
        if count == 0:
            return "0 versions"
        ct = ContentType.objects.get_for_model(obj)
        url = reverse("admin:core_modelversion_changelist") + f"?content_type__id__exact={ct.pk}&object_id={obj.pk}"
        return format_html('<a href="{}">{} version{}</a>', url, count, "s" if count != 1 else "")


class TimestampedAdminMixin:
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for field in ("created_at", "updated_at", "deleted_at"):
            if hasattr(self.model, field) and field not in readonly:
                readonly.append(field)
        return readonly

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if hasattr(self.model, "created_at") and "created_at" not in list_display:
            list_display.append("created_at")
        return list_display


# ---------------------------------------------------------------------------
# Export mixins
# ---------------------------------------------------------------------------


def _serialize_export_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "pk"):
        return str(value.pk)
    return str(value) if value is not None else None


class ImportExportMixin:
    export_filename_prefix = "export"
    import_form_template = None

    @admin.action(description="Export selected items as JSON")
    def export_as_json(self, request, queryset):
        data = []
        for obj in queryset:
            if hasattr(self, "serialize_for_export"):
                data.append(self.serialize_for_export(obj))
                continue
            item = {field.name: _serialize_export_value(getattr(obj, field.name)) for field in obj._meta.fields}
            data.append(item)
        response = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json")
        filename = f"{self.export_filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions["export_as_json"] = (self.export_as_json, "export_as_json", "Export selected items as JSON")
        return actions


class ExportMixin:
    @admin.action(description="Export to CSV")
    def export_to_csv(self, request, queryset):
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{self.model._meta.model_name}.csv"'
        writer = csv.writer(response)
        field_names = [field.name for field in self.model._meta.fields]
        writer.writerow(field_names)
        for obj in queryset:
            row = []
            for field in field_names:
                value = getattr(obj, field)
                if isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                elif hasattr(value, "pk"):
                    value = str(value)
                row.append(value)
            writer.writerow(row)
        return response

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions["export_to_csv"] = (self.export_to_csv, "export_to_csv", "Export to CSV")
        return actions
