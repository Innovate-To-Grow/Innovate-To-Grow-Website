from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from ..models import NewsArticle
from ..services import sync_news


@admin.register(NewsArticle)
class NewsArticleAdmin(ModelAdmin):
    list_display = ("title", "published_at", "source", "created_at")
    list_filter = ("source", "published_at")
    search_fields = ("title", "summary")
    readonly_fields = ("source_guid", "raw_payload", "created_at", "updated_at")
    ordering = ("-published_at",)

    def get_urls(self):
        custom_urls = [
            path("sync/", self.admin_site.admin_view(self.sync_view), name="news_newsarticle_sync"),
        ]
        return custom_urls + super().get_urls()

    def sync_view(self, request):
        result = sync_news()
        msg = f"Sync complete: {result['created']} created, {result['updated']} updated."
        if result["errors"]:
            msg += f" {len(result['errors'])} error(s)."
            messages.warning(request, msg)
        else:
            messages.success(request, msg)
        return HttpResponseRedirect(reverse("admin:news_newsarticle_changelist"))

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["sync_url"] = reverse("admin:news_newsarticle_sync")
        return super().changelist_view(request, extra_context=extra_context)
