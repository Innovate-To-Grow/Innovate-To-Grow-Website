"""The current projects shown on the schedule."""

from django.contrib import admin

from apps.core.admin import BaseModelAdmin

from ...models import CurrentProject


@admin.register(CurrentProject)
class CurrentProjectAdmin(BaseModelAdmin):
    list_display = (
        "class_code",
        "team_number",
        "team_name",
        "project_title",
        "organization",
        "is_presenting",
        "schedule",
    )
    list_editable = ("is_presenting",)
    list_filter = ("is_presenting", "class_code", "schedule")
    search_fields = ("team_number", "team_name", "project_title", "organization")
    list_per_page = 200

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
