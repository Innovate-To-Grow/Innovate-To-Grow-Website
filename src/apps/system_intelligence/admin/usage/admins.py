"""The usage log admins: conversations with their transcript, and single messages."""

from django.contrib import admin
from django.utils.html import format_html, format_html_join
from unfold.admin import TabularInline
from unfold.decorators import display

from apps.core.admin import ReadOnlyModelAdmin
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog

from .formatting import _SOURCE_COLORS, _STATUS_COLORS, _transcript_turn


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

    @display(description="Source", label=_SOURCE_COLORS)
    def source_badge(self, obj):
        return obj.source, obj.get_source_display()

    @admin.display(description="Conversation")
    def conversation_transcript(self, obj):
        messages = list(obj.messages.all())
        if not messages:
            return format_html(
                '<div class="si-transcript-empty">{}</div>',
                "No messages recorded for this conversation.",
            )

        turns = [_transcript_turn(index, message) for index, message in enumerate(messages, start=1)]
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

    @display(description="Status", label=_STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @admin.display(description="Tokens")
    def token_total(self, obj):
        return (obj.token_usage or {}).get("totalTokens") or 0

    @admin.display(description="Prompt")
    def prompt_short(self, obj):
        return obj.prompt[:80] + "..." if len(obj.prompt) > 80 else obj.prompt
