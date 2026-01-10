from django.contrib import admin

from ..models import HomePage, PageComponent
from .page_component import PageComponentForm


class HomePageComponentInline(admin.StackedInline):
    model = PageComponent
    fk_name = "home_page"
    extra = 0
    form = PageComponentForm
    fields = (
        "name",
        "component_type",
        "order",
        "is_enabled",
        "html_content",
        "css_code",
        "js_code",
        "config",
        "form",
        "image",
        "image_alt",
        "background_image",
        "data_source",
        "data_params",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("order", "id")
    show_change_link = True


@admin.register(HomePage)
class HomePageAdmin(admin.ModelAdmin):
    inlines = [HomePageComponentInline]
    list_display = ("name", "is_active", "component_count", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

    def component_count(self, obj):
        return obj.components.count()

    component_count.short_description = "Components"
