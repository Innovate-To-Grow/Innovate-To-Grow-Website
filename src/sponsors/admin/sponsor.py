from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from ..models import Sponsor


@admin.register(Sponsor)
class SponsorAdmin(ModelAdmin):
    list_display = ("name", "year", "display_order", "logo_preview_small", "website")
    list_filter = ("year",)
    list_editable = ("display_order",)
    search_fields = ("name",)
    readonly_fields = ("logo_preview", "created_at", "updated_at")
    ordering = ("-year", "display_order", "name")

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "year", "website", "logo", "logo_preview", "display_order"),
            },
        ),
        (
            "System",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Logo")
    def logo_preview_small(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="max-height:30px;max-width:80px;" />', obj.logo.url)
        return "-"

    @admin.display(description="Logo Preview")
    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="max-height:120px;max-width:300px;" />', obj.logo.url)
        return "No logo uploaded"
