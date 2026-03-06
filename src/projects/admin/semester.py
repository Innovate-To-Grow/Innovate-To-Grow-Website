import logging

from django.contrib import admin, messages
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from ..models import Project, Semester
from ..services.import_excel import import_projects_from_excel

logger = logging.getLogger(__name__)


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
    change_list_template = "admin/projects/semester_changelist.html"

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

    def get_urls(self):
        custom_urls = [
            path("import-excel/", self.admin_site.admin_view(self.import_excel_view), name="projects_import_excel"),
        ]
        return custom_urls + super().get_urls()

    def import_excel_view(self, request):
        context = {**self.admin_site.each_context(request), "title": "Import Projects from Excel"}

        if request.method == "POST":
            excel_file = request.FILES.get("excel_file")
            if not excel_file:
                context["error"] = "Please select a file to upload."
                return render(request, "admin/projects/import_excel.html", context)

            if not excel_file.name.endswith(".xlsx"):
                context["error"] = "Only .xlsx files are supported."
                return render(request, "admin/projects/import_excel.html", context)

            try:
                stats = import_projects_from_excel(excel_file)
                context["stats"] = stats
                messages.success(
                    request,
                    format_html(
                        "Imported <strong>{}</strong> projects ({} created, {} updated) across <strong>{}</strong> semesters.",
                        stats["projects_created"] + stats["projects_updated"],
                        stats["projects_created"],
                        stats["projects_updated"],
                        stats["semesters_created"] + stats["semesters_existing"],
                    ),
                )
            except ValueError as e:
                context["error"] = str(e)
            except Exception:
                logger.exception("Excel import failed")
                context["error"] = "An unexpected error occurred during import. Check the server logs."

        return render(request, "admin/projects/import_excel.html", context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_url"] = reverse("admin:projects_import_excel")
        return super().changelist_view(request, extra_context=extra_context)
