from typing import Any

from core.services.system_intelligence_actions.exceptions import ActionRequestError

from ..query_helpers import object_payload, queryset_payload, require_one
from ..runtime import run_action_service_async


async def get_news_source_detail(
    source_id: str | None = None,
    source_key: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Get news feed source status and recent sync counters."""
    return await run_action_service_async(_get_news_source_detail, source_id, source_key, name)


def _get_news_source_detail(source_id=None, source_key=None, name=None) -> dict[str, Any]:
    from cms.models import NewsArticle, NewsFeedSource

    qs = NewsFeedSource.objects.all()
    if source_id:
        source = require_one(qs.filter(pk=source_id), "News source")
    elif source_key:
        source = require_one(qs.filter(source_key=source_key), "News source")
    elif name:
        source = require_one(qs.filter(name__icontains=name), "News source")
    else:
        raise ActionRequestError("Provide source_id, source_key, or name.")
    article_qs = NewsArticle.objects.filter(source=source.source_key)
    return {
        "source": object_payload(
            source,
            [
                "id",
                "name",
                "source_key",
                "feed_url",
                "is_active",
                "last_synced_at",
                "last_sync_created",
                "last_sync_updated",
                "last_sync_errors",
                "updated_at",
            ],
        ),
        "article_count": article_qs.count(),
        "recent_articles": queryset_payload(
            article_qs.order_by("-published_at"), ["id", "title", "published_at"], limit=10
        )["rows"],
    }
