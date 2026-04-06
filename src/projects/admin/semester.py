from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import path, reverse
from unfold.admin import TabularInline

from core.admin import BaseModelAdmin

from ..models import Project, Semester
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
        ]
        return custom_urls + super().get_urls()

    def publish_all_view(self, request):
        if request.method == "POST":
            updated = Semester.objects.filter(is_published=False).update(is_published=True)
            transaction.on_commit(_clear_project_caches)
            self.message_user(request, f"{updated} semester(s) published.", messages.SUCCESS)
        return redirect(reverse("admin:projects_semester_changelist"))

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["publish_all_url"] = reverse("admin:projects_publish_all")
        return super().changelist_view(request, extra_context=extra_context)
