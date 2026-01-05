from django.contrib import admin

from ..models import Page, PageComponent
from .page_component import PageComponentForm


class PageComponentInline(admin.StackedInline):
    model = PageComponent
    fk_name = "page"
    extra = 0
    form = PageComponentForm
    fields = ("component_type", "order", "html_content", "config", "css_file", "css_code", "js_code", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at", "css_file")
    ordering = ("order", "id")
    show_change_link = True


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    inlines = [PageComponentInline]
    list_display = ("title", "slug", "published", "view_count", "updated_at")
    list_filter = ("published", "created_at")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("page_uuid", "slug_depth", "view_count", "last_viewed_at", "created_at", "updated_at")

    fieldsets = (
        ("Basic Information", {"fields": ("title", "slug", "page_uuid")}),
        ("Rendering", {"fields": ("template_name",), "classes": ("extrapretty",)}),
        (
            "SEO & Metadata",
            {
                "fields": (
                    "meta_title",
                    "meta_description",
                    "meta_keywords",
                    "og_image",
                    "canonical_url",
                    "meta_robots",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Publishing",
            {
                "fields": ("published", "created_at", "updated_at"),
            },
        ),
        ("Statistics", {"fields": ("view_count", "last_viewed_at", "slug_depth"), "classes": ("collapse",)}),
    )
