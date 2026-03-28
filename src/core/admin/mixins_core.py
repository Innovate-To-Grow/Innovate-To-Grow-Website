"""Core admin mixins unrelated to export formats."""

from django.contrib import admin, messages
from django.utils.html import format_html


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
        return format_html(
            '<a href="#" onclick="alert(\'Version history coming soon\'); return false;">{} versions</a>', count
        )


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
