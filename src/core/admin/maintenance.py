from django.contrib import admin
from unfold.admin import ModelAdmin

from core.models import SiteMaintenanceControl


@admin.register(SiteMaintenanceControl)
class SiteMaintenanceControlAdmin(ModelAdmin):
    list_display = ("__str__", "is_maintenance", "updated_at")
    fields = ("is_maintenance", "message", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        # Only allow one instance (singleton)
        if SiteMaintenanceControl.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False
