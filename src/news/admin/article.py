from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import NewsArticle


@admin.register(NewsArticle)
class NewsArticleAdmin(ModelAdmin):
    list_display = ("title", "published_at", "source", "created_at")
    list_filter = ("source", "published_at")
    search_fields = ("title", "summary")
    readonly_fields = ("source_guid", "raw_payload", "created_at", "updated_at")
    ordering = ("-published_at",)
