from django.contrib import admin

from core.admin import BaseModelAdmin

from ..models import Project


@admin.register(Project)
class ProjectAdmin(BaseModelAdmin):
    list_display = ("project_title", "semester", "class_code", "team_number", "organization", "industry")
    list_filter = ("semester", "class_code", "industry")
    search_fields = ("project_title", "team_name", "organization", "student_names")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Team",
            {
                "fields": ("semester", "class_code", "team_number", "team_name"),
            },
        ),
        (
            "Project",
            {
                "fields": ("project_title", "organization", "industry", "abstract"),
            },
        ),
        (
            "Members",
            {
                "fields": ("student_names",),
            },
        ),
        (
            "Event Scheduling",
            {
                "classes": ("collapse",),
                "fields": ("track", "presentation_order"),
            },
        ),
        (
            "System",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )
