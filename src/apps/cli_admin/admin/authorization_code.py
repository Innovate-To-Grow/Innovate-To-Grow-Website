from django.contrib import admin

from apps.core.admin import ReadOnlyModelAdmin

from ..models import CliAuthorizationCode


@admin.register(CliAuthorizationCode)
class CliAuthorizationCodeAdmin(ReadOnlyModelAdmin):
    """Read-only listing of CLI authorization codes. The code hash is never displayed."""

    list_display = ("member", "is_used", "is_expired_display", "created_at", "expires_at", "used_at")
    list_filter = ("is_used",)
    list_select_related = ("member",)
    ordering = ("-created_at",)

    @admin.display(description="Expired", boolean=True)
    def is_expired_display(self, obj):
        return obj.is_expired
