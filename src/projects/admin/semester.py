from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import TabularInline

from core.admin import BaseModelAdmin

from ..models import Project, Semester
from ..services.csv_import import import_projects_from_csv
from ..signals import _clear_project_caches


class ProjectInline(TabularInline):
    model = Project
    extra = 0
    fields = ("team_number", "team_name", "project_title", "organization", "class_code")
    readonly_fields = ("created_at",)


@admin.register(Semester)
class SemesterAdmin(BaseModelAdmin):
    list_display = ("label", "year", "season", "is_published", "project_count", "updated_at")
    list_filter = ("is_published", "season", "year")
    readonly_fields = ("label", "created_at", "updated_at")
    inlines = [ProjectInline]
    change_list_template = "admin/projects/semester_changelist.html"
    actions = ["publish_selected", "unpublish_selected"]

    @admin.action(description="Publish selected semesters")
    def publish_selected(self, request, queryset):
        updated = queryset.filter(is_published=False).update(is_published=True)
        transaction.on_commit(_clear_project_caches)
        self.message_user(request, f"{updated} semester(s) published.", messages.SUCCESS)

    @admin.action(description="Unpublish selected semesters")
    def unpublish_selected(self, request, queryset):
        updated = queryset.filter(is_published=True).update(is_published=False)
        transaction.on_commit(_clear_project_caches)
        self.message_user(request, f"{updated} semester(s) unpublished.", messages.SUCCESS)

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
            path("publish-all/", self.admin_site.admin_view(self.publish_all_view), name="projects_publish_all"),
            path("import-csv/", self.admin_site.admin_view(self.import_csv_view), name="projects_import_csv"),
        ]
        return custom_urls + super().get_urls()

    def publish_all_view(self, request):
        if request.method == "POST":
            updated = Semester.objects.filter(is_published=False).update(is_published=True)
            transaction.on_commit(_clear_project_caches)
            self.message_user(request, f"{updated} semester(s) published.", messages.SUCCESS)
        return redirect(reverse("admin:projects_semester_changelist"))

    def import_csv_view(self, request):
        if request.method == "POST":
            csv_file = request.FILES.get("csv_file")
            if not csv_file:
                self.message_user(request, "No file uploaded.", messages.ERROR)
                return redirect(reverse("admin:projects_semester_changelist"))

            dry_run = bool(request.POST.get("dry_run"))
            publish = bool(request.POST.get("publish"))

            result = import_projects_from_csv(csv_file, dry_run=dry_run, publish=publish)

            prefix = "[DRY RUN] " if dry_run else ""
            self.message_user(
                request,
                f"{prefix}{result.created} project(s) created, {result.skipped} skipped.",
                messages.SUCCESS,
            )
            for error in result.errors[:20]:
                self.message_user(request, error, messages.WARNING)
            if not dry_run and result.created:
                transaction.on_commit(_clear_project_caches)

            return redirect(reverse("admin:projects_semester_changelist"))

        return TemplateResponse(
            request,
            "admin/projects/import_csv.html",
            {
                **self.admin_site.each_context(request),
                "title": "Import Projects from CSV",
            },
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["publish_all_url"] = reverse("admin:projects_publish_all")
        extra_context["import_csv_url"] = reverse("admin:projects_import_csv")
        return super().changelist_view(request, extra_context=extra_context)
