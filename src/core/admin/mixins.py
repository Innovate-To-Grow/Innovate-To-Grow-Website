"""
Admin mixins for common functionality.
"""

import json
from datetime import datetime

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html


class SoftDeleteAdminMixin:
    """
    Mixin for models with soft delete functionality.

    Adds actions and filters for managing soft-deleted records.
    """

    def get_queryset(self, request):
        """Include soft-deleted records if requested."""
        qs = super().get_queryset(request)
        if hasattr(self.model, "all_objects"):
            # Use all_objects manager to include soft-deleted
            return self.model.all_objects.all()
        return qs

    def get_list_display(self, request):
        """Add is_deleted indicator to list display."""
        list_display = list(super().get_list_display(request))
        if hasattr(self.model, "is_deleted") and "deletion_status" not in list_display:
            list_display.append("deletion_status")
        return list_display

    @admin.display(description="Status", boolean=False)
    def deletion_status(self, obj):
        """Show deletion status with color coding."""
        if not hasattr(obj, "is_deleted"):
            return "-"

        if obj.is_deleted:
            return format_html('<span style="color: red;">✗ Deleted</span>')
        return format_html('<span style="color: green;">✓ Active</span>')

    def get_list_filter(self, request):
        """Add is_deleted filter."""
        filters = list(super().get_list_filter(request))
        if hasattr(self.model, "is_deleted"):
            filters.insert(0, "is_deleted")
        return filters

    @admin.action(description="Restore selected items")
    def restore_selected(self, request, queryset):
        """Action to restore soft-deleted items."""
        restored = 0
        for obj in queryset:
            if hasattr(obj, "restore") and obj.is_deleted:
                obj.restore()
                restored += 1

        if restored:
            messages.success(request, f"Successfully restored {restored} item(s).")
        else:
            messages.warning(request, "No items were restored.")

    @admin.action(description="Soft delete selected items")
    def soft_delete_selected(self, request, queryset):
        """Action to soft delete items."""
        deleted = 0
        for obj in queryset:
            if not obj.is_deleted:
                obj.delete()  # Uses soft delete by default
                deleted += 1

        if deleted:
            messages.success(request, f"Successfully soft deleted {deleted} item(s).")
        else:
            messages.warning(request, "No items were deleted.")

    def get_actions(self, request):
        """Add restore action for soft-deleted models."""
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
    """
    Mixin for models with version control functionality.
    """

    def save_model(self, request, obj, form, change):
        """Save a version when model is saved."""
        super().save_model(request, obj, form, change)

        if hasattr(obj, "save_version") and change:
            # Save version after update
            comment = f"Updated via admin by {request.user.username}"
            obj.save_version(comment=comment, user=request.user)

    @admin.display(description="Versions")
    def version_count(self, obj):
        """Display number of versions."""
        if hasattr(obj, "get_versions"):
            versions = obj.get_versions()
            count = versions.count() if versions else 0
            return format_html(
                '<a href="#" onclick="alert(\'Version history coming soon\'); return false;">{} versions</a>', count
            )
        return "-"


class TimestampedAdminMixin:
    """
    Mixin for models with created_at and updated_at fields.
    """

    def get_readonly_fields(self, request, obj=None):
        """Make timestamp fields readonly."""
        readonly = list(super().get_readonly_fields(request, obj))
        timestamp_fields = ["created_at", "updated_at", "deleted_at"]

        for field in timestamp_fields:
            if hasattr(self.model, field) and field not in readonly:
                readonly.append(field)

        return readonly

    def get_list_display(self, request):
        """Add timestamps to list display."""
        list_display = list(super().get_list_display(request))

        # Add created_at if not present
        if hasattr(self.model, "created_at") and "created_at" not in list_display:
            list_display.append("created_at")

        return list_display


class ImportExportMixin:
    """
    Mixin to add import/export functionality to admin.
    """

    # Override these in subclasses
    export_filename_prefix = "export"
    import_form_template = None

    @admin.action(description="Export selected items as JSON")
    def export_as_json(self, request, queryset):
        """Export selected items as JSON."""
        data = []
        for obj in queryset:
            if hasattr(self, "serialize_for_export"):
                data.append(self.serialize_for_export(obj))
            else:
                # Default serialization
                item = {}
                for field in obj._meta.fields:
                    value = getattr(obj, field.name)
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    elif hasattr(value, "pk"):  # Foreign key
                        value = str(value.pk)
                    else:
                        value = str(value) if value is not None else None
                    item[field.name] = value
                data.append(item)

        response = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json")
        filename = f"{self.export_filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def get_actions(self, request):
        """Add export action."""
        actions = super().get_actions(request)
        actions["export_as_json"] = (self.export_as_json, "export_as_json", "Export selected items as JSON")
        return actions


class ExportMixin:
    """
    Simplified mixin for export-only functionality.
    """

    @admin.action(description="Export to CSV")
    def export_to_csv(self, request, queryset):
        """Export queryset to CSV."""
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{self.model._meta.model_name}.csv"'

        writer = csv.writer(response)

        # Write headers
        field_names = [field.name for field in self.model._meta.fields]
        writer.writerow(field_names)

        # Write data
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
        """Add export action."""
        actions = super().get_actions(request)
        actions["export_to_csv"] = (self.export_to_csv, "export_to_csv", "Export to CSV")
        return actions
