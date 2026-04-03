from django.contrib import admin

from cms.models import NewsArticle
from core.admin import BaseModelAdmin


@admin.register(NewsArticle)
class NewsArticleAdmin(BaseModelAdmin):
    list_display = ("title", "published_at", "source", "created_at")
    list_filter = ("source", "published_at")
    search_fields = ("title", "summary")
    readonly_fields = ("source_guid", "raw_payload", "created_at", "updated_at")
    ordering = ("-published_at",)

    fieldsets = (
        (
            "Article",
            {
                "fields": ("title", "source", "source_url", "source_guid", "author", "published_at"),
            },
        ),
        (
            "Content",
            {
                "fields": ("summary", "image_url", "hero_image_url", "hero_caption", "content"),
            },
        ),
        (
            "System",
            {
                "classes": ("collapse",),
                "fields": ("raw_payload", "created_at", "updated_at"),
            },
        ),
    )
