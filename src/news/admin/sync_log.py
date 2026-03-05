from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import NewsSyncLog


@admin.register(NewsSyncLog)
class NewsSyncLogAdmin(ModelAdmin):
    list_display = (
        "feed_source",
        "started_at",
        "duration_seconds",
        "articles_created",
        "articles_updated",
        "has_errors_display",
    )
    list_filter = ("feed_source",)
    readonly_fields = (
        "feed_source",
        "started_at",
        "duration_seconds",
        "articles_created",
        "articles_updated",
        "errors_text",
    )
    ordering = ("-started_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_errors_display(self, obj):
        return obj.has_errors

    has_errors_display.boolean = True
    has_errors_display.short_description = "Errors?"
