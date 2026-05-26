from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html

from core.admin import BaseModelAdmin
from miniapps.models import MiniApp, MiniAppDataSchema


class MiniAppDataSchemaInline(admin.StackedInline):
    model = MiniAppDataSchema
    extra = 0
    max_num = 1
    fields = ("fields",)
    verbose_name = "Data Schema"
    verbose_name_plural = "Data Schema"


@admin.register(MiniApp)
class MiniAppAdmin(BaseModelAdmin):
    change_form_template = "admin/miniapps/miniapp/change_form.html"

    list_display = ("title", "url_path", "status", "embeddable", "record_count", "updated_at")
    list_filter = ("status", "embeddable")
    search_fields = ("title", "slug", "url_path")
    readonly_fields = ("id", "created_at", "updated_at", "preview_link")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [MiniAppDataSchemaInline]

    fieldsets = (
        ("App Info", {"fields": ("title", "slug", "url_path", "description", "icon", "status", "embeddable")}),
        ("Code", {"fields": ("html_code", "js_code", "css_code"), "classes": ("miniapp-code-fields",)}),
        ("Metadata", {"fields": ("id", "created_at", "updated_at", "preview_link")}),
    )

    class Media:
        css = {"all": ("miniapps/css/editor.css",)}
        js = ("miniapps/js/editor.js",)

    def record_count(self, obj):
        return obj.records.count()

    record_count.short_description = "Records"

    def preview_link(self, obj):
        if obj.pk and obj.status == "published":
            url = reverse("miniapp-code", kwargs={"app_slug": obj.slug})
            return format_html('<a href="{}" target="_blank">Open Preview</a>', url)
        return "Publish to enable preview"

    preview_link.short_description = "Preview"

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/preview/",
                self.admin_site.admin_view(self.preview_view),
                name="miniapps_miniapp_preview",
            ),
        ]
        return custom_urls + super().get_urls()

    def preview_view(self, request, object_id):
        from django.http import JsonResponse

        app = self.get_object(request, object_id)
        if not app:
            return JsonResponse({"error": "Not found"}, status=404)
        from miniapps.services.renderer import render_miniapp_document

        html = render_miniapp_document(app)
        return JsonResponse({"html": html})
