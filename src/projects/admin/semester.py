from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from ..models import Project, Semester


class ProjectInline(TabularInline):
    model = Project
    extra = 0
    fields = ("team_number", "team_name", "project_title", "organization", "class_code")
    readonly_fields = ("created_at",)


@admin.register(Semester)
class SemesterAdmin(ModelAdmin):
    list_display = ("label", "year", "season", "is_published", "project_count", "updated_at")
    list_filter = ("is_published", "season", "year")
    readonly_fields = ("label", "created_at", "updated_at")
    inlines = [ProjectInline]

    fieldsets = (
        (
            "Semester Info",
            {
                "fields": ("year", "season", "label", "is_published"),
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

    @admin.display(description="Projects")
    def project_count(self, obj):
        return obj.projects.count()
