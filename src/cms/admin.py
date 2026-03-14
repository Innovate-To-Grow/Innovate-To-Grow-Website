from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline

from .models import CMSBlock, CMSPage


class CMSBlockInline(StackedInline):
    model = CMSBlock
    extra = 0
    fields = ["block_type", "sort_order", "admin_label", "data"]
    ordering = ["sort_order"]


@admin.register(CMSPage)
class CMSPageAdmin(ModelAdmin):
    list_display = ("title", "route", "status", "block_count", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "slug", "route")
    readonly_fields = ("created_at", "updated_at", "published_at")
    inlines = [CMSBlockInline]

    fieldsets = (
        (
            "Page Info",
            {
                "fields": (
                    "slug",
                    "route",
                    "title",
                    "meta_description",
                    "page_css_class",
                    "status",
                    "sort_order",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("published_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def block_count(self, obj):
        return obj.blocks.filter(is_deleted=False).count()

    block_count.short_description = "Blocks"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Prevent slug changes on published pages to preserve export stability
        if obj and obj.status == "published":
            readonly.append("slug")
        return readonly
