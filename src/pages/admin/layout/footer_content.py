import json

from django.contrib import admin
from unfold.admin import ModelAdmin

from ...app_routes import APP_ROUTES
from ...models import FooterContent


@admin.register(FooterContent)
class FooterContentAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    change_form_template = "admin/pages/footer_content/change_form.html"

    fieldsets = (
        (None, {"fields": ("name", "slug", "is_active")}),
        ("Footer Content", {"fields": ("content",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["app_routes_json"] = json.dumps(APP_ROUTES)
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["app_routes_json"] = json.dumps(APP_ROUTES)
        return super().add_view(request, form_url, extra_context)
