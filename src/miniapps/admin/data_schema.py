from django.contrib import admin

from core.admin import BaseModelAdmin
from miniapps.models import MiniAppDataSchema


@admin.register(MiniAppDataSchema)
class MiniAppDataSchemaAdmin(BaseModelAdmin):
    list_display = ("app", "field_count", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")

    def field_count(self, obj):
        return len(obj.fields) if obj.fields else 0

    field_count.short_description = "Fields"
