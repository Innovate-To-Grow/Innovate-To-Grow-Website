import json

from django.contrib import admin
from unfold.admin import ModelAdmin

from ...app_routes import APP_ROUTES
from ...models import CMSPage, FooterContent


@admin.register(FooterContent)
class FooterContentAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    change_list_template = "admin/cms/footer_content/change_list.html"
    change_form_template = "admin/cms/footer_content/change_form.html"

    fieldsets = (
        (None, {"fields": ("name", "slug", "is_active")}),
        ("Footer Content", {"fields": ("content",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    # noinspection PyMethodMayBeStatic
    def _get_editor_context(self):
        cms_pages = list(CMSPage.objects.filter(status="published").order_by("title").values("route", "title"))
        cms_routes = [{"url": p["route"], "title": p["title"]} for p in cms_pages]
        return {
            "app_routes_json": json.dumps(APP_ROUTES),
            "cms_routes_json": json.dumps(cms_routes),
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_editor_context()}
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_editor_context()}
        return super().add_view(request, form_url, extra_context)
