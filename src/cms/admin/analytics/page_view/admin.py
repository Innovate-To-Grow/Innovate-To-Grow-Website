"""Django admin for CMS page-view analytics."""

from django.contrib import admin
from django.core.cache import cache
from django.urls import path
from django.utils.html import format_html

from cms.models import PageView
from core.admin import ReadOnlyModelAdmin

from .geo import ip_geo_lookup_view
from .stats import DASHBOARD_CACHE_KEY, DASHBOARD_CACHE_TTL, compute_dashboard_stats


@admin.register(PageView)
class PageViewAdmin(ReadOnlyModelAdmin):
    change_list_template = "admin/cms/pageview/change_list.html"
    list_display = ("path", "short_referrer", "ip_display", "user_agent_short", "timestamp")
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

    class Media:
        css = {"all": ("admin/css/ip-geo-popup.css",)}

    fieldsets = (
        ("Request", {"fields": ("id", "path", "referrer", "timestamp")}),
        ("Visitor", {"fields": ("member", "ip_address", "session_key", "user_agent")}),
    )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        cached = cache.get(DASHBOARD_CACHE_KEY)
        if cached is None:
            cached = compute_dashboard_stats()
            cache.set(DASHBOARD_CACHE_KEY, cached, DASHBOARD_CACHE_TTL)
        extra_context.update(cached)
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
            return obj.member.get_primary_email() or str(obj.member.id)
        return "-"

    @admin.display(description="User Agent")
    def user_agent_short(self, obj):
        if not obj.user_agent:
            return "-"
        ua = obj.user_agent
        if len(ua) > 60:
            return format_html('<span title="{}">{}&hellip;</span>', ua, ua[:60])
        return ua

    @admin.display(description="Session")
    def session_key_short(self, obj):
        if not obj.session_key:
            return "-"
        return f"{obj.session_key[:8]}..."

    @admin.display(description="IP Address")
    def ip_display(self, obj):
        if not obj.ip_address:
            return "-"
        return format_html(
            '<span class="ip-geo-link" data-ip="{ip}" style="cursor:pointer;border-bottom:1px dashed currentColor"'
            ' title="Click to look up location">{ip}</span>',
            ip=obj.ip_address,
        )

    def get_urls(self):
        return [
            path(
                "ip-geo-lookup/",
                self.admin_site.admin_view(ip_geo_lookup_view),
                name="cms_pageview_ip_geo_lookup",
            ),
        ] + super().get_urls()
