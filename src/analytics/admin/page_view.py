from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from analytics.models import PageView


@admin.register(PageView)
class PageViewAdmin(ModelAdmin):
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
