from django.contrib import admin, messages
from django.db.models import Count, OuterRef, Subquery
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timesince import timesince
from unfold.admin import TabularInline
from unfold.decorators import action, display

from apps.cms.models import NewsArticle, NewsFeedSource, NewsSyncLog
from apps.cms.services.news import sync_feed_sources
from apps.core.admin import BaseModelAdmin


class NewsSyncLogInline(TabularInline):
    model = NewsSyncLog
    fields = ("started_at", "duration_seconds", "articles_created", "articles_updated", "errors_text")
    readonly_fields = ("started_at", "duration_seconds", "articles_created", "articles_updated", "errors_text")
    ordering = ("-started_at",)
    extra = 0
    max_num = 0
    can_delete = False


@admin.register(NewsFeedSource)
class NewsFeedSourceAdmin(BaseModelAdmin):
    list_display = (
        "name",
        "source_key",
        "status_badge",
        "article_count_display",
        "sync_result_badge",
        "time_since_sync",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "feed_url", "source_key")
    readonly_fields = (
        "last_synced_at",
        "last_sync_created",
        "last_sync_updated",
        "last_sync_errors",
        "created_at",
        "updated_at",
    )
    actions_list = ["sync_all_feeds"]
    actions_detail = ["sync_this_feed"]
    inlines = [NewsSyncLogInline]

    fieldsets = (
        (
            "Feed Configuration",
            {
                "fields": ("name", "source_key", "feed_url", "is_active"),
            },
        ),
        (
            "Last Sync Status",
            {
                "fields": ("last_synced_at", "last_sync_created", "last_sync_updated", "last_sync_errors"),
            },
        ),
        (
            "Timestamps",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            # NewsArticle stores this stable identifier rather than a foreign key.
            # Renaming it after creation would orphan the existing source mapping.
            fields.append("source_key")
        return tuple(fields)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    @display(description="Last Sync", label=True)
    def sync_result_badge(self, obj):
        if obj.last_sync_errors:
            diagnostics = [line.strip() for line in obj.last_sync_errors.splitlines() if line.strip()]
            if diagnostics and all(line.startswith("Warning: ") for line in diagnostics):
                return "Warnings", "warning"
            return "Errors", "warning"
        if not obj.last_synced_at:
            return "Never synced", "info"
        return "Success", "success"

    @display(description="Synced")
    def time_since_sync(self, obj):
        if not obj.last_synced_at:
            return "-"
        return f"{timesince(obj.last_synced_at)} ago"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        article_count_sq = (
            NewsArticle.objects.filter(source=OuterRef("source_key"))
            .order_by()
            .values("source")
            .annotate(cnt=Count("id"))
            .values("cnt")
        )
        return qs.annotate(_article_count=Subquery(article_count_sq))

    @display(description="Articles")
    def article_count_display(self, obj):
        count = getattr(obj, "_article_count", None) or 0
        url = reverse("admin:cms_newsarticle_changelist") + f"?source={obj.source_key}"
        return format_html('<a href="{}">{}</a>', url, count)

    @action(description="Sync all active feeds", url_path="sync-all-feeds", icon="sync")
    def sync_all_feeds(self, request):
        sources = NewsFeedSource.objects.filter(is_active=True)
        if not sources.exists():
            messages.warning(request, "No active feed sources found.")
            return HttpResponseRedirect(reverse("admin:cms_newsfeedsource_changelist"))

        result = sync_feed_sources(sources)

        msg = (
            f"Sync complete: {result['created']} created, {result['updated']} updated "
            f"across {result['feed_count']} feed(s)."
        )
        if result["errors"]:
            msg += f" {len(result['errors'])} error(s)."
        if result["warnings"]:
            msg += f" {len(result['warnings'])} warning(s)."
        if result["errors"] or result["warnings"]:
            messages.warning(request, msg)
        else:
            messages.success(request, msg)
        return HttpResponseRedirect(reverse("admin:cms_newsfeedsource_changelist"))

    @action(description="Sync this feed", url_path="sync-this-feed", icon="sync")
    def sync_this_feed(self, request, object_id):
        source = NewsFeedSource.objects.get(id=object_id)
        if not source.is_active:
            messages.warning(request, f"Feed '{source.name}' is not active.")
            return HttpResponseRedirect(reverse("admin:cms_newsfeedsource_change", args=[object_id]))

        result = sync_feed_sources([source])

        msg = f"Sync complete for '{source.name}': {result['created']} created, {result['updated']} updated."
        if result["errors"]:
            msg += f" {len(result['errors'])} error(s)."
        if result["warnings"]:
            msg += f" {len(result['warnings'])} warning(s)."
        if result["errors"] or result["warnings"]:
            messages.warning(request, msg)
        else:
            messages.success(request, msg)
        return HttpResponseRedirect(reverse("admin:cms_newsfeedsource_change", args=[object_id]))
