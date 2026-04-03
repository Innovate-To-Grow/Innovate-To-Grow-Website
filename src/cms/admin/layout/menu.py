import json

from django.contrib import admin

from core.admin import BaseModelAdmin

from ...app_routes import APP_ROUTES
from ...models import CMSPage, Menu


@admin.register(Menu)
class MenuAdmin(BaseModelAdmin):
    list_display = ("name", "is_active", "items_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    change_form_template = "admin/cms/menu/change_form.html"

    fieldsets = (
        (None, {"fields": ("name", "description", "is_active")}),
        ("Menu Items", {"fields": ("items",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    # noinspection PyMethodMayBeStatic
    def _get_editor_context(self):
        """Build context with app routes and CMS pages for the menu editor."""
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

    def items_count(self, obj):
        """Count total items including children."""

        def count_items(items):
            if not items:
                return 0
            count = len(items)
            for item in items:
                if item.get("children"):
                    count += count_items(item["children"])
            return count

        return count_items(obj.items or [])

    items_count.short_description = "Items"

    def save_model(self, request, obj, form, change):
        """Auto-populate display_name from name if not set."""
        if not obj.display_name:
            # Convert slug to title case (e.g., 'main_nav' -> 'Main Nav')
            obj.display_name = obj.name.replace("_", " ").replace("-", " ").title()
        super().save_model(request, obj, form, change)
