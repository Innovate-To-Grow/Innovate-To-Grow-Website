"""Admin mixins for timestamps and export formats."""

import json
from datetime import datetime

from django.contrib import admin
from django.http import HttpResponse

# ---------------------------------------------------------------------------
# Core mixins
# ---------------------------------------------------------------------------


class TimestampedAdminMixin:
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for field in ("created_at", "updated_at"):
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
