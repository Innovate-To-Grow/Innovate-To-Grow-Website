import json

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from ...models import Page
from ..shared.base import WorkflowAdminMixin
from .import_export import deserialize_page, serialize_page


@admin.register(Page)
class PageAdmin(WorkflowAdminMixin, ModelAdmin):
    change_form_template = "admin/pages/page/grapesjs_editor.html"
    change_list_template = "admin/pages/page/change_list.html"
    list_display = ("title", "slug", "status_badge", "view_count", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("status", "published_at", "published_by")

    fieldsets = (
        (None, {"fields": ("title", "slug", "template_name")}),
        ("Publishing", {"fields": ("status", "published_at", "published_by")}),
        ("SEO", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    actions = ["action_submit_for_review", "action_publish", "action_unpublish", "action_export_json"]

    def get_display_name(self, obj):
        return obj.title

    # ========================
    # Import / Export
    # ========================

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("import/", self.admin_site.admin_view(self.import_view), name="pages_page_import"),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_url"] = reverse("admin:pages_page_import")
        return super().changelist_view(request, extra_context=extra_context)

    def import_view(self, request):
        """Handle JSON import for Pages."""
        context = {**self.admin_site.each_context(request), "title": "Import Page JSON"}

        if request.method == "POST":
            json_file = request.FILES.get("json_file")
            if not json_file:
                context["error"] = "No file uploaded."
                return TemplateResponse(request, "admin/pages/page/import_form.html", context)

            try:
                data = json.load(json_file)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                context["error"] = f"Invalid JSON file: {e}"
                return TemplateResponse(request, "admin/pages/page/import_form.html", context)

            items = data if isinstance(data, list) else [data]
            all_warnings = []
            imported_count = 0

            for item in items:
                if item.get("export_type") != "page":
                    all_warnings.append(
                        f"Skipped entry with export_type='{item.get('export_type')}' (expected 'page')."
                    )
                    continue
                try:
                    page, warnings = deserialize_page(item, user=request.user)
                    all_warnings.extend(warnings)
                    imported_count += 1
                except Exception as e:
                    all_warnings.append(f"Error importing page: {e}")

            if imported_count:
                self.message_user(request, f"Successfully imported {imported_count} page(s).", messages.SUCCESS)
            if all_warnings:
                context["warnings"] = all_warnings
                return TemplateResponse(request, "admin/pages/page/import_form.html", context)

            return HttpResponseRedirect(reverse("admin:pages_page_changelist"))

        return TemplateResponse(request, "admin/pages/page/import_form.html", context)

    @admin.action(description="Export selected pages as JSON")
    def action_export_json(self, request, queryset):
        pages = list(queryset)
        if len(pages) == 1:
            data = serialize_page(pages[0])
            filename = f"page-{pages[0].slug.replace('/', '-')}.json"
        else:
            data = [serialize_page(p) for p in pages]
            filename = "pages-export.json"

        response = HttpResponse(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
