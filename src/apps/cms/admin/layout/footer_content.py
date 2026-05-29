from django.contrib import admin

from core.admin import BaseModelAdmin

from ...models import FooterContent
from .route_options import build_route_editor_context


@admin.register(FooterContent)
class FooterContentAdmin(BaseModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    change_form_template = "admin/cms/footer_content/change_form.html"

    fieldsets = (
        (None, {"fields": ("name", "slug", "is_active")}),
        ("Footer Content", {"fields": ("content",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    # noinspection PyMethodMayBeStatic
    def _get_editor_context(self):
        return build_route_editor_context()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_editor_context()}
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_editor_context()}
        return super().add_view(request, form_url, extra_context)
