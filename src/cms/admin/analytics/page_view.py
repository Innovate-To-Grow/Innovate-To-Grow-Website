from datetime import timedelta

from django.contrib import admin
from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from cms.models import PageView

_DASHBOARD_CACHE_KEY = "cms:analytics:dashboard"
_DASHBOARD_CACHE_TTL = 60  # seconds


@admin.register(PageView)
class PageViewAdmin(ModelAdmin):
    change_list_template = "admin/cms/pageview/change_list.html"
    list_display = ("path", "short_referrer", "ip_address", "member_display", "session_key_short", "timestamp")
    list_filter = ("timestamp",)
    search_fields = (
        "path",
        "referrer",
        "ip_address",
        "session_key",
        "member__contact_emails__email_address",
        "member__first_name",
        "member__last_name",
    )
    readonly_fields = ("id", "path", "referrer", "user_agent", "ip_address", "member", "session_key", "timestamp")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page = 50
    list_select_related = ("member",)

    fieldsets = (
        ("Request", {"fields": ("id", "path", "referrer", "timestamp")}),
        ("Visitor", {"fields": ("member", "ip_address", "session_key", "user_agent")}),
    )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        cached = cache.get(_DASHBOARD_CACHE_KEY)
        if cached is None:
            cached = self._compute_dashboard_stats()
            cache.set(_DASHBOARD_CACHE_KEY, cached, _DASHBOARD_CACHE_TTL)
        extra_context.update(cached)
        return super().changelist_view(request, extra_context=extra_context)

    @staticmethod
    def _compute_dashboard_stats():
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

        # Daily breakdown for the past 7 days
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

        # Unique visitors per day (second dataset for the 7-day chart)
        daily_visitors = (
            qs.filter(timestamp__gte=seven_days_ago)
            .annotate(date=TruncDate("timestamp"))
            .values("date")
            .annotate(visitor_count=Count("ip_address", distinct=True))
            .order_by("date")
        )
        visitor_map = {entry["date"]: entry["visitor_count"] for entry in daily_visitors}
        stats["last_7_days_visitors"] = [visitor_map.get(d["date"], 0) for d in last_7_days]

        # Hourly breakdown for today
        hourly_qs = (
            qs.filter(timestamp__gte=today_start)
            .annotate(hour=TruncHour("timestamp"))
            .values("hour")
            .annotate(count=Count("id"))
            .order_by("hour")
        )
        hourly_map = {entry["hour"].hour: entry["count"] for entry in hourly_qs}
        stats["hourly_views"] = [{"hour": h, "count": hourly_map.get(h, 0)} for h in range(24)]

        # Top referrers (excluding direct / empty)
        stats["top_referrers"] = list(
            qs.exclude(referrer="").values("referrer").annotate(ref_count=Count("id")).order_by("-ref_count")[:10]
        )

        return stats

    @admin.display(description="Referrer")
    def short_referrer(self, obj):
        if not obj.referrer:
            return "-"
        if len(obj.referrer) > 50:
            return format_html('<span title="{}">{}&hellip;</span>', obj.referrer, obj.referrer[:50])
        return obj.referrer

    @admin.display(description="Member")
    def member_display(self, obj):
        if obj.member:
            return obj.member.get_primary_email() or str(obj.member.id)
        return "-"

    @admin.display(description="Session")
    def session_key_short(self, obj):
        if not obj.session_key:
            return "-"
        return f"{obj.session_key[:8]}…"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
