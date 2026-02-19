import json

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from ...models import HomePage
from ..shared.base import CompactComponentInline, WorkflowAdminMixin
from .import_export import deserialize_homepage, serialize_homepage


class HomePageComponentInline(CompactComponentInline):
    fk_name = "home_page"


@admin.register(HomePage)
class HomePageAdmin(WorkflowAdminMixin, ModelAdmin):
    inlines = [HomePageComponentInline]
    change_form_template = "admin/pages/shared_change_form.html"
    change_list_template = "admin/pages/homepage/change_list.html"
    list_display = ("name", "is_active", "status_badge", "component_count", "created_at", "updated_at")
    list_filter = ("is_active", "status", "created_at")
    search_fields = ("name",)
    readonly_fields = ("status", "published_at", "published_by")

    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("Publishing", {"fields": ("status", "published_at", "published_by")}),
    )

    actions = ["action_submit_for_review", "action_publish", "action_unpublish", "action_export_json"]

    def get_display_name(self, obj):
        return obj.name

    # ========================
    # Import / Export
    # ========================

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("import/", self.admin_site.admin_view(self.import_view), name="pages_homepage_import"),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_url"] = reverse("admin:pages_homepage_import")
        return super().changelist_view(request, extra_context=extra_context)

    def import_view(self, request):
        """Handle JSON import for HomePages."""
        context = {**self.admin_site.each_context(request), "title": "Import HomePage JSON"}

        if request.method == "POST":
            json_file = request.FILES.get("json_file")
            if not json_file:
                context["error"] = "No file uploaded."
                return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

            try:
                data = json.load(json_file)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                context["error"] = f"Invalid JSON file: {e}"
                return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

            items = data if isinstance(data, list) else [data]
            all_warnings = []
            imported_count = 0

            for item in items:
                if item.get("export_type") != "homepage":
                    all_warnings.append(
                        f"Skipped entry with export_type='{item.get('export_type')}' (expected 'homepage')."
                    )
                    continue
                try:
                    homepage, warnings = deserialize_homepage(item, user=request.user)
                    all_warnings.extend(warnings)
                    imported_count += 1
                except Exception as e:
                    all_warnings.append(f"Error importing homepage: {e}")

            if imported_count:
                self.message_user(request, f"Successfully imported {imported_count} home page(s).", messages.SUCCESS)
            if all_warnings:
                context["warnings"] = all_warnings
                return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

            return HttpResponseRedirect(reverse("admin:pages_homepage_changelist"))

        return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

    @admin.action(description="Export selected home pages as JSON")
    def action_export_json(self, request, queryset):
        homepages = list(queryset)
        if len(homepages) == 1:
            data = serialize_homepage(homepages[0])
            filename = f"homepage-{homepages[0].name.replace(' ', '-').lower()}.json"
        else:
            data = [serialize_homepage(hp) for hp in homepages]
            filename = "homepages-export.json"

        response = HttpResponse(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
