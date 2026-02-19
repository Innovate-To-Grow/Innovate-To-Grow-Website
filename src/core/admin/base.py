"""
Base admin classes for consistent admin interface across the project.
"""

from unfold.admin import ModelAdmin


class BaseModelAdmin(ModelAdmin):
    """
    Base admin class with common configuration for all model admins.

    Provides:
    - Unfold theme integration
    - Common readonly fields for ProjectControlModel
    - Standard list display configuration
    """

    # Common readonly fields for ProjectControlModel
    readonly_fields_base = ("id", "created_at", "updated_at")

    # Standard list configuration
    list_per_page = 50

    def get_readonly_fields(self, request, obj=None):
        """Include base readonly fields with any model-specific ones."""
        readonly = list(super().get_readonly_fields(request, obj))

        # Add base fields if model has them
        if hasattr(self.model, "created_at"):
            for field in self.readonly_fields_base:
                if hasattr(self.model, field) and field not in readonly:
                    readonly.append(field)

        return readonly

    def has_add_permission(self, request):
        """Check if user has permission to add objects."""
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        """Check if user has permission to change objects."""
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        """Check if user has permission to delete objects."""
        return super().has_delete_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        """Check if user has permission to view objects."""
        return super().has_view_permission(request, obj)


class ReadOnlyModelAdmin(BaseModelAdmin):
    """
    Admin class for read-only models.

    Useful for audit logs, system records, or any model that should
    not be edited through the admin interface.
    """

    def has_add_permission(self, request):
        """Prevent adding new objects."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent changing objects."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting objects."""
        return False

    def get_actions(self, request):
        """Remove all actions."""
        actions = super().get_actions(request)
        if actions and "delete_selected" in actions:
            del actions["delete_selected"]
        return actions
