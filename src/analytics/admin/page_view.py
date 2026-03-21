from datetime import timedelta

from django.contrib import admin
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from analytics.models import PageView


@admin.register(PageView)
class PageViewAdmin(ModelAdmin):
    change_list_template = "admin/analytics/pageview/change_list.html"
    list_display = ("path", "short_referrer", "ip_address", "member_display", "session_key_short", "timestamp")
    list_filter = ("timestamp",)
    search_fields = (
        "path",
        "referrer",
        "ip_address",
        "session_key",
        "member__email",
        "member__first_name",
        "member__last_name",
    )
    readonly_fields = ("id", "path", "referrer", "user_agent", "ip_address", "member", "session_key", "timestamp")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page = 50
    list_select_related = ("member",)

    fieldsets = (
        (
            "Request",
            {
                "fields": ("id", "path", "referrer", "timestamp"),
            },
        ),
        (
            "Visitor",
            {
                "fields": ("member", "ip_address", "session_key", "user_agent"),
            },
        ),
    )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = today_start - timedelta(days=6)

        qs = PageView.objects.all()

        # Summary stats
        extra_context["total_views"] = qs.count()
        extra_context["today_views"] = qs.filter(timestamp__gte=today_start).count()
        extra_context["unique_paths"] = qs.values("path").distinct().count()
        extra_context["unique_visitors"] = qs.values("ip_address").distinct().count()

        # Top 10 pages
        extra_context["top_pages"] = qs.values("path").annotate(view_count=Count("id")).order_by("-view_count")[:10]

        # Views over last 7 days (fill missing days with 0)
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
        extra_context["last_7_days"] = last_7_days
        extra_context["max_daily_count"] = max((d["count"] for d in last_7_days), default=1) or 1

        return super().changelist_view(request, extra_context=extra_context)

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
            return obj.member.email
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
