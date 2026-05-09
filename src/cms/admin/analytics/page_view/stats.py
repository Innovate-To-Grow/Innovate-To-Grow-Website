"""Dashboard statistics for page-view analytics admin."""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from cms.models import PageView

DASHBOARD_CACHE_KEY = "cms:analytics:dashboard"
DASHBOARD_CACHE_TTL = 300


def compute_dashboard_stats():
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = today_start - timedelta(days=6)

    qs = PageView.objects.order_by()
    stats = {
        "total_views": qs.count(),
        "today_views": qs.filter(timestamp__gte=today_start).count(),
        "unique_paths": qs.values("path").distinct().count(),
        "unique_visitors": qs.values("ip_address").distinct().count(),
        "top_pages": list(qs.values("path").annotate(view_count=Count("id")).order_by("-view_count")[:10]),
    }
    _add_daily_stats(stats, qs, seven_days_ago)
    _add_hourly_stats(stats, qs, today_start)
    stats["top_referrers"] = list(
        qs.exclude(referrer="").values("referrer").annotate(ref_count=Count("id")).order_by("-ref_count")[:10]
    )
    return stats


def _add_daily_stats(stats, qs, seven_days_ago):
    daily_views = (
        qs.filter(timestamp__gte=seven_days_ago)
        .annotate(date=TruncDate("timestamp"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    daily_map = {entry["date"]: entry["count"] for entry in daily_views}
    last_7_days = []
    for i in range(7):
        day = (seven_days_ago + timedelta(days=i)).date()
        last_7_days.append({"date": day, "count": daily_map.get(day, 0)})
    stats["last_7_days"] = last_7_days
    stats["max_daily_count"] = max((d["count"] for d in last_7_days), default=1) or 1

    week_views = sum(d["count"] for d in last_7_days)
    stats["week_views"] = week_views
    stats["avg_daily_views"] = round(week_views / 7, 1)

    daily_visitors = (
        qs.filter(timestamp__gte=seven_days_ago)
        .annotate(date=TruncDate("timestamp"))
        .values("date")
        .annotate(visitor_count=Count("ip_address", distinct=True))
        .order_by("date")
    )
    visitor_map = {entry["date"]: entry["visitor_count"] for entry in daily_visitors}
    stats["last_7_days_visitors"] = [visitor_map.get(d["date"], 0) for d in last_7_days]


def _add_hourly_stats(stats, qs, today_start):
    hourly_qs = (
        qs.filter(timestamp__gte=today_start)
        .annotate(hour=TruncHour("timestamp"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )
    hourly_map = {entry["hour"].hour: entry["count"] for entry in hourly_qs}
    stats["hourly_views"] = [{"hour": h, "count": hourly_map.get(h, 0)} for h in range(24)]
