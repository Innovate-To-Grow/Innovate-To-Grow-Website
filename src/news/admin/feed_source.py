import logging

from django.contrib import admin, messages
from django.utils import timezone
from unfold.admin import ModelAdmin
from unfold.decorators import action

from ..models import NewsFeedSource
from ..services import sync_news

logger = logging.getLogger(__name__)


@admin.register(NewsFeedSource)
class NewsFeedSourceAdmin(ModelAdmin):
    list_display = ("name", "feed_url", "is_active", "last_synced_at", "last_sync_created", "last_sync_updated")
    list_filter = ("is_active",)
    search_fields = ("name", "feed_url")
    readonly_fields = ("last_synced_at", "last_sync_created", "last_sync_updated", "last_sync_errors", "created_at", "updated_at")
    actions_list = ["sync_selected_feeds"]

    @action(description="Sync selected feeds", url_path="sync-selected-feeds")
    def sync_selected_feeds(self, request, object_ids=None):
        if object_ids:
            sources = NewsFeedSource.objects.filter(id__in=object_ids, is_active=True)
        else:
            sources = NewsFeedSource.objects.filter(is_active=True)

        if not sources.exists():
            messages.warning(request, "No active feed sources selected.")
            return

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

        msg = f"Sync complete: {total_created} created, {total_updated} updated across {sources.count()} feed(s)."
        if total_errors:
            msg += f" {len(total_errors)} error(s)."
            messages.warning(request, msg)
        else:
            messages.success(request, msg)
