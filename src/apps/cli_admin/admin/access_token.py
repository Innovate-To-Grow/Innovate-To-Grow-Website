from django.contrib import admin
from django.utils import timezone
from unfold.decorators import display

from apps.core.admin import ReadOnlyModelAdmin

from ..models import CliAccessToken


@admin.register(CliAccessToken)
class CliAccessTokenAdmin(ReadOnlyModelAdmin):
    """Read-only listing of CLI bearer tokens with a revoke kill-switch.

    The raw token and its hash are never displayed.
    """

    list_display = ("member", "validity", "created_at", "expires_at", "revoked_at", "last_used_at", "created_ip")
    list_filter = ("revoked_at",)
    list_select_related = ("member",)
    search_fields = ("member__username", "created_ip")
    ordering = ("-created_at",)
    actions = ["revoke_selected"]

    @display(description="Status", label=True)
    def validity(self, obj):
        if obj.is_valid:
            return "valid", "success"
        if obj.is_revoked:
            return "revoked", "danger"
        return "expired", "warning"

    @admin.action(description="Revoke selected tokens")
    def revoke_selected(self, request, queryset):
        count = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        self.message_user(request, f"Revoked {count} token(s).")
