from django.contrib import admin

from core.admin import BaseModelAdmin
from miniapps.models import MiniAppDataRecord


@admin.register(MiniAppDataRecord)
class MiniAppDataRecordAdmin(BaseModelAdmin):
    list_display = ("id", "app", "created_by", "created_at")
    list_filter = ("app",)
    search_fields = ("app__title",)
    readonly_fields = ("id", "app", "created_by", "created_at", "updated_at")
    fields = ("app", "data", "created_by", "created_at", "updated_at")
