"""
Base admin classes for consistent admin interface across the project.
"""

from django.db.models.constants import LOOKUP_SEP
from unfold.admin import ModelAdmin

from apps.core.utils.access import user_is_admin

from ..confirmation.post_data import SENSITIVE_FIELD_RE
from ..mixins import ConfirmOnSaveMixin, DataExportMixin, TimestampedAdminMixin


class BaseModelAdmin(ConfirmOnSaveMixin, DataExportMixin, TimestampedAdminMixin, ModelAdmin):
    """
    Base admin class with common configuration for all model admins.

    Provides:
    - Unfold theme integration
    - Common readonly fields for ProjectControlModel
    - Timestamp readonly fields
    - Standard list display configuration
    - Admin access control (see apps.core.utils.access.user_is_admin): every
      Admin (an active staff member) may view, add, change and delete every
      model; nobody else may. Django's per-model codename permissions are not
      consulted.
    """

    # Common readonly fields for ProjectControlModel
    readonly_fields_base = ("id", "created_at", "updated_at")

    # Standard list configuration
    list_per_page = 50

    def _has_app_access(self, request) -> bool:
        """Whether the request's user is an Admin (the name is kept for subclasses that call it)."""
        return user_is_admin(request.user)

    def has_module_permission(self, request):
        return self._has_app_access(request)

    def has_view_permission(self, request, obj=None):
        return self._has_app_access(request)

    def has_add_permission(self, request):
        return self._has_app_access(request)

    def has_change_permission(self, request, obj=None):
        return self._has_app_access(request)

    def has_delete_permission(self, request, obj=None):
        return self._has_app_access(request)

    def lookup_allowed(self, lookup, value, request=None):
        """Refuse changelist filters on secret-looking fields (``?password__startswith=a`` → 400).

        Django allows a query-string lookup on any local field, so the result count would answer guesses about a
        stored secret one character at a time, and the guesses would land in the access log. The names follow the
        same rule as the confirmation diff and the CLI denylist (``SENSITIVE_FIELD_RE``).
        """
        if SENSITIVE_FIELD_RE.search(str(lookup).split(LOOKUP_SEP, 1)[0]):
            return False
        return super().lookup_allowed(lookup, value, request)

    def get_readonly_fields(self, request, obj=None):
        """Include base readonly fields with any model-specific ones."""
        readonly = list(super().get_readonly_fields(request, obj))

        # Add base fields if model has them
        if hasattr(self.model, "created_at"):
            for field in self.readonly_fields_base:
                if hasattr(self.model, field) and field not in readonly:
                    readonly.append(field)

        return readonly


class AppAccessInlineMixin:
    """Admin access for inlines — the inline counterpart of ``BaseModelAdmin``'s rule.

    Django's stock inline permissions ask for per-model codenames (``event.change_eventagendaitem``); this mixin
    makes an inline follow the project's rule instead: every Admin may view, add, change and delete it
    (see ``apps.core.utils.access.user_is_admin``). Inlines that need more (an ownership check on the parent, a
    safety rail) override the write methods.
    """

    def _has_app_access(self, request) -> bool:
        """Whether the request's user is an Admin (the name is kept for subclasses that call it)."""
        return user_is_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return self._has_app_access(request)

    def has_add_permission(self, request, obj=None):
        return self._has_app_access(request)

    def has_change_permission(self, request, obj=None):
        return self._has_app_access(request)

    def has_delete_permission(self, request, obj=None):
        return self._has_app_access(request)


class ReadOnlyModelAdmin(BaseModelAdmin):
    """
    Admin class for read-only models.

    Useful for audit logs, system records, or any model that should
    not be edited through the admin interface.
    """

    require_confirmation = False

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
