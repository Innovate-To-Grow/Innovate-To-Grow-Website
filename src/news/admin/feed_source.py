from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from unfold.admin import ModelAdmin
from unfold.decorators import action

from ..models import NewsFeedSource
from ..services import sync_news


@admin.register(NewsFeedSource)
class NewsFeedSourceAdmin(ModelAdmin):
    list_display = ("name", "feed_url", "is_active", "last_synced_at", "last_sync_created", "last_sync_updated")
    list_filter = ("is_active",)
    search_fields = ("name", "feed_url")
    readonly_fields = ("last_synced_at", "last_sync_created", "last_sync_updated", "last_sync_errors", "created_at", "updated_at")
    actions_list = ["sync_all_feeds"]
    actions_detail = ["sync_this_feed"]

    @action(description="Sync all active feeds", url_path="sync-all-feeds", icon="sync")
    def sync_all_feeds(self, request):
        sources = NewsFeedSource.objects.filter(is_active=True)
        if not sources.exists():
            messages.warning(request, "No active feed sources found.")
            return HttpResponseRedirect(reverse("admin:news_newsfeedsource_changelist"))

        total_created, total_updated, total_errors = self._sync_sources(sources)

        msg = f"Sync complete: {total_created} created, {total_updated} updated across {sources.count()} feed(s)."
        if total_errors:
            msg += f" {len(total_errors)} error(s)."
            messages.warning(request, msg)
        else:
            messages.success(request, msg)
        return HttpResponseRedirect(reverse("admin:news_newsfeedsource_changelist"))

    @action(description="Sync this feed", url_path="sync-this-feed", icon="sync")
    def sync_this_feed(self, request, object_id):
        source = NewsFeedSource.objects.get(id=object_id)
        if not source.is_active:
            messages.warning(request, f"Feed '{source.name}' is not active.")
            return HttpResponseRedirect(reverse("admin:news_newsfeedsource_change", args=[object_id]))

        total_created, total_updated, total_errors = self._sync_sources([source])

        msg = f"Sync complete for '{source.name}': {total_created} created, {total_updated} updated."
        if total_errors:
            msg += f" {len(total_errors)} error(s)."
            messages.warning(request, msg)
        else:
            messages.success(request, msg)
        return HttpResponseRedirect(reverse("admin:news_newsfeedsource_change", args=[object_id]))

    @staticmethod
    def _sync_sources(sources):
        total_created = 0
        total_updated = 0
        total_errors = []

        for source in sources:
            result = sync_news(feed_url=source.feed_url)
            total_created += result["created"]
            total_updated += result["updated"]
            total_errors.extend(result["errors"])

            source.last_synced_at = timezone.now()
            source.last_sync_created = result["created"]
            source.last_sync_updated = result["updated"]
            source.last_sync_errors = "\n".join(result["errors"]) if result["errors"] else ""
            source.save(update_fields=[
                "last_synced_at", "last_sync_created", "last_sync_updated", "last_sync_errors",
            ])

        return total_created, total_updated, total_errors
