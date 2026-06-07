import json

from django.contrib import admin
from django.template.defaultfilters import linebreaksbr
from django.utils import timezone
from django.utils.html import format_html, format_html_join
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


def _token_value(usage, key):
    if not isinstance(usage, dict):
        return 0
    try:
        return int(usage.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _linebreaks(value):
    return linebreaksbr(str(value or "—"))


def _pretty_json(value):
    if not value:
        return ""
    return json.dumps(value, indent=2, sort_keys=True)


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
    readonly_fields = (
        "id",
        "source",
        "session_id",
        "ip_hash",
        "user",
        "message_count",
        "total_tokens",
        "last_activity_at",
        "created_at",
        "updated_at",
        "conversation_transcript",
    )
    fieldsets = (
        (
            "Overview",
            {
                "fields": (
                    "id",
                    "source",
                    "session_id",
                    "user",
                    "ip_hash",
                    "message_count",
                    "total_tokens",
                    "last_activity_at",
                )
            },
        ),
        ("Conversation Transcript", {"fields": ("conversation_transcript",)}),
        ("System Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("messages")

    @admin.display(description="Session")
    def session_short(self, obj):
        if not obj.session_id:
            return "—"
        return str(obj.session_id)[:8]

    @display(description="Source", label=True)
    def source_badge(self, obj):
        return obj.get_source_display(), _SOURCE_COLORS.get(obj.source, "info")

    @admin.display(description="Conversation")
    def conversation_transcript(self, obj):
        messages = list(obj.messages.all())
        if not messages:
            return format_html(
                '<div class="si-transcript-empty">{}</div>',
                "No messages recorded for this conversation.",
            )

        turns = []
        for index, message in enumerate(messages, start=1):
            usage = message.token_usage or {}
            meta = [
                f"Turn {index}",
                message.get_status_display(),
                f"Total: {_token_value(usage, 'totalTokens'):,}",
                f"Input: {_token_value(usage, 'inputTokens'):,}",
                f"Output: {_token_value(usage, 'outputTokens'):,}",
                f"Latency: {message.latency_ms:,} ms",
            ]
            if message.model_id:
                meta.append(message.model_id)
            if message.created_at:
                meta.append(timezone.localtime(message.created_at).strftime("%Y-%m-%d %H:%M:%S %Z"))

            meta_html = format_html_join("", '<span class="si-transcript-chip">{}</span>', ((item,) for item in meta))
            reply_html = (
                format_html(
                    """
                    <div class="si-transcript-block si-transcript-block--assistant">
                      <div class="si-transcript-label">Assistant</div>
                      <div class="si-transcript-text">{}</div>
                    </div>
                    """,
                    _linebreaks(message.reply),
                )
                if message.reply
                else ""
            )
            results_html = (
                format_html(
                    """
                    <div class="si-transcript-block">
                      <div class="si-transcript-label">Results</div>
                      <pre class="si-transcript-json">{}</pre>
                    </div>
                    """,
                    _pretty_json(message.results),
                )
                if message.results
                else ""
            )
            turns.append(
                format_html(
                    """
                    <article class="si-transcript-turn">
                      <div class="si-transcript-meta">{}</div>
                      <div class="si-transcript-block si-transcript-block--user">
                        <div class="si-transcript-label">User</div>
                        <div class="si-transcript-text">{}</div>
                      </div>
                      {}{}
                    </article>
                    """,
                    meta_html,
                    _linebreaks(message.prompt),
                    reply_html,
                    results_html,
                )
            )

        transcript = format_html_join("", "{}", ((turn,) for turn in turns))
        return format_html('<div class="si-transcript">{}</div>', transcript)


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
