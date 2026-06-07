from django.contrib import admin
from unfold.admin import TabularInline
from unfold.decorators import display

from apps.core.admin import ReadOnlyModelAdmin
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog

_SOURCE_COLORS = {
    AssistantConversationLog.SOURCE_PUBLIC_CHAT: "info",
    AssistantConversationLog.SOURCE_AI_SEARCH: "primary",
}
_STATUS_COLORS = {
    AssistantMessageLog.STATUS_OK: "success",
    AssistantMessageLog.STATUS_ERROR: "danger",
    AssistantMessageLog.STATUS_BUDGET: "warning",
    AssistantMessageLog.STATUS_UNAVAILABLE: "info",
}


class AssistantMessageLogInline(TabularInline):
    """Read-only per-turn detail inside a conversation."""

    model = AssistantMessageLog
    fields = ("prompt_short", "reply", "status", "token_total", "created_at")
    readonly_fields = fields
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Prompt")
    def prompt_short(self, obj):
        return obj.prompt[:80] + "..." if len(obj.prompt) > 80 else obj.prompt

    @admin.display(description="Tokens")
    def token_total(self, obj):
        return (obj.token_usage or {}).get("totalTokens") or 0


@admin.register(AssistantConversationLog)
class AssistantConversationLogAdmin(ReadOnlyModelAdmin):
    """Read-only, conversation-grouped audit of assistant turns."""

    list_display = (
        "session_short",
        "source_badge",
        "user",
        "message_count",
        "total_tokens",
        "last_activity_at",
    )
    list_filter = ("source", "last_activity_at")
    list_select_related = ("user",)
    search_fields = ("session_id", "ip_hash", "messages__prompt", "user__email")
    date_hierarchy = "last_activity_at"
    ordering = ("-last_activity_at",)
    inlines = [AssistantMessageLogInline]

    @admin.display(description="Session")
    def session_short(self, obj):
        if not obj.session_id:
            return "—"
        return str(obj.session_id)[:8]

    @display(description="Source", label=True)
    def source_badge(self, obj):
        return obj.get_source_display(), _SOURCE_COLORS.get(obj.source, "info")


@admin.register(AssistantMessageLog)
class AssistantMessageLogAdmin(ReadOnlyModelAdmin):
    """Read-only, flat per-message audit view."""

    list_display = ("created_at", "status_badge", "model_id", "token_total", "latency_ms", "prompt_short")
    list_filter = ("status", "created_at")
    list_select_related = ("conversation",)
    search_fields = ("prompt", "reply")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        return obj.get_status_display(), _STATUS_COLORS.get(obj.status, "info")

    @admin.display(description="Tokens")
    def token_total(self, obj):
        return (obj.token_usage or {}).get("totalTokens") or 0

    @admin.display(description="Prompt")
    def prompt_short(self, obj):
        return obj.prompt[:80] + "..." if len(obj.prompt) > 80 else obj.prompt
