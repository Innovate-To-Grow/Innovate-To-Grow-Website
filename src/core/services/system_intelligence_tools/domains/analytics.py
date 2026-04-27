from typing import Any

from django.db.models import Count
from django.db.models.functions import TruncDay, TruncHour, TruncMonth

from core.services.system_intelligence_actions.utils import json_safe

from ..query_helpers import apply_date_range, bounded_limit, queryset_payload
from ..runtime import run_action_service_async


async def get_page_view_summary(
    path: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Summarize page views by optional path and date range."""
    return await run_action_service_async(_get_page_view_summary, path, date_from, date_to)


async def get_top_paths(
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return top visited paths for a date range."""
    return await run_action_service_async(_get_top_paths, date_from, date_to, limit)


async def get_page_view_trend(
    path: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    granularity: str | None = "day",
    limit: int | None = None,
) -> dict[str, Any]:
    """Return page-view counts grouped by hour, day, or month."""
    return await run_action_service_async(_get_page_view_trend, path, date_from, date_to, granularity, limit)


def _page_view_queryset(path=None, date_from=None, date_to=None):
    from cms.models import PageView

    qs = PageView.objects.all()
    if path:
        qs = qs.filter(path__icontains=path)
    return apply_date_range(qs, "timestamp", date_from, date_to)


def _get_page_view_summary(path=None, date_from=None, date_to=None) -> dict[str, Any]:
    qs = _page_view_queryset(path, date_from, date_to)
    return {
        "filters": {"path": path, "date_from": date_from, "date_to": date_to},
        "total_views": qs.count(),
        "unique_paths": qs.values("path").distinct().count(),
        "known_members": qs.exclude(member_id=None).values("member_id").distinct().count(),
        "sessions": qs.exclude(session_key="").values("session_key").distinct().count(),
        "recent_views": queryset_payload(
            qs.order_by("-timestamp"), ["path", "member_id", "session_key", "timestamp"], limit=10
        )["rows"],
    }


def _get_top_paths(date_from=None, date_to=None, limit=None) -> dict[str, Any]:
    qs = _page_view_queryset(date_from=date_from, date_to=date_to)
    row_limit = bounded_limit(limit)
    rows = list(qs.values("path").annotate(views=Count("id")).order_by("-views", "path")[:row_limit])
    return {
        "filters": {"date_from": date_from, "date_to": date_to},
        "shown": len(rows),
        "total_paths": qs.values("path").distinct().count(),
        "rows": json_safe(rows),
    }


def _get_page_view_trend(path=None, date_from=None, date_to=None, granularity="day", limit=None) -> dict[str, Any]:
    qs = _page_view_queryset(path, date_from, date_to)
    trunc = {"hour": TruncHour, "day": TruncDay, "month": TruncMonth}.get((granularity or "day").lower(), TruncDay)
    row_limit = bounded_limit(limit, default=30)
    rows = list(
        qs.annotate(period=trunc("timestamp"))
        .values("period")
        .annotate(views=Count("id"))
        .order_by("-period")[:row_limit]
    )
    rows.reverse()
    return {
        "filters": {"path": path, "date_from": date_from, "date_to": date_to, "granularity": granularity or "day"},
        "shown": len(rows),
        "rows": json_safe(rows),
    }
