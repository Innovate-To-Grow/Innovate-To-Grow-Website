from django.contrib import admin

from cms.models import CMSEmbedAllowedHost
from cms.services.embed_hosts import invalidate_cache
from core.admin import BaseModelAdmin


@admin.register(CMSEmbedAllowedHost)
class CMSEmbedAllowedHostAdmin(BaseModelAdmin):
    list_display = ("hostname", "description", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("hostname", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Host",
            {
                "fields": ("hostname", "description", "is_active"),
                "description": (
                    "Hosts that may appear as the src of CMS 'embed' blocks. "
                    "Use an exact host like 'docs.google.com' or a wildcard like '*.youtube.com'."
                ),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidate_cache()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        invalidate_cache()

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        invalidate_cache()
