"""Admin views for System Intelligence and SystemIntelligenceConfig model admin."""

import json
import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect, JsonResponse, StreamingHttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminTextareaWidget

from core.admin.base import BaseModelAdmin
from core.models.base.system_intelligence import ChatConversation, ChatMessage, SystemIntelligenceConfig
from core.services.bedrock import invoke_bedrock_stream

logger = logging.getLogger(__name__)


def _tool_calls_for_storage(stream_events):
    """Normalize streamed tool_call dicts for JSONField (UI expects name, input, result_preview)."""
    out = []
    for ev in stream_events:
        if not isinstance(ev, dict):
            continue
        inp = ev.get("input")
        if inp is not None and not isinstance(inp, dict):
            inp = {}
        out.append(
            {
                "name": ev.get("name", "unknown"),
                "input": inp or {},
                "result_preview": ev.get("result_preview") or "",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Standalone chat views (registered via AppConfig.ready monkey-patch)
# ---------------------------------------------------------------------------


def get_system_intelligence_urls():
    """Return URL patterns for the System Intelligence admin views."""
    return [
        path(
            "core/system-intelligence/",
            admin.site.admin_view(chat_list_view),
            name="core_system_intelligence",
        ),
        path(
            "core/system-intelligence/conversations/",
            admin.site.admin_view(conversations_fragment),
            name="core_system_intelligence_conversations",
        ),
        path(
            "core/system-intelligence/new/",
            admin.site.admin_view(new_conversation_view),
            name="core_system_intelligence_new",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/",
            admin.site.admin_view(chat_view),
            name="core_system_intelligence_detail",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/send/",
            admin.site.admin_view(chat_send_view),
            name="core_system_intelligence_send",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/delete/",
            admin.site.admin_view(chat_delete_view),
            name="core_system_intelligence_delete",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/rename/",
            admin.site.admin_view(chat_rename_view),
            name="core_system_intelligence_rename",
        ),
    ]


def _resolve_model_name(model_id):
    """Return a friendly display name for a Bedrock model ID, or the raw ID."""
    if not model_id:
        return "Not configured"
    try:
        from core.services.bedrock import get_available_models

        for _group, models in get_available_models():
            for mid, name in models:
                if mid == model_id:
                    return name
    except Exception:
        logger.exception("Failed to resolve model display name for '%s'.", model_id)
    return model_id


def chat_list_view(request):
    """Render the main AI chat shell page."""
    from core.models import AWSCredentialConfig
    from core.services.db_tools import get_tool_definitions

    si_config = SystemIntelligenceConfig.load()
    aws_config = AWSCredentialConfig.load()

    model_id = aws_config.default_model_id
    model_name = _resolve_model_name(model_id)

    tools = [
        {"name": t["toolSpec"]["name"], "description": t["toolSpec"]["description"]} for t in get_tool_definitions()
    ]

    # Build admin edit URLs (changelist if unsaved, change page if saved)
    si_url = (
        reverse("admin:core_systemintelligenceconfig_change", args=[si_config.pk])
        if si_config.pk
        else reverse("admin:core_systemintelligenceconfig_changelist")
    )
    aws_url = (
        reverse("admin:core_awscredentialconfig_change", args=[aws_config.pk])
        if aws_config.pk
        else reverse("admin:core_awscredentialconfig_changelist")
    )

    context = {
        **admin.site.each_context(request),
        "title": "System Intelligence",
        "si_config": si_config,
        "aws_config": aws_config,
        "model_id": model_id or "",
        "model_name": model_name,
        "tools": tools,
        "tool_count": len(tools),
        "si_config_url": si_url,
        "aws_config_url": aws_url,
    }
    return TemplateResponse(request, "admin/core/system_intelligence.html", context)


def conversations_fragment(request):
    """Return JSON list of conversations for the current user."""
    convos = ChatConversation.objects.filter(created_by=request.user).values("id", "title", "updated_at")
    data = [
        {
            "id": str(c["id"]),
            "title": c["title"],
            "updated_at": c["updated_at"].strftime("%b %d, %H:%M"),
        }
        for c in convos
    ]
    return JsonResponse({"conversations": data})


def new_conversation_view(request):
    """Create a new conversation and return its ID."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    convo = ChatConversation.objects.create(created_by=request.user)
    return JsonResponse({"id": str(convo.id), "title": convo.title})


def chat_view(request, conversation_id):
    """Return JSON messages for a conversation."""
    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)

    msgs = convo.messages.values("id", "role", "content", "model_id", "created_at", "tool_calls", "token_usage")
    data = [
        {
            "id": str(m["id"]),
            "role": m["role"],
            "content": m["content"],
            "model_id": m["model_id"],
            "created_at": m["created_at"].strftime("%b %d, %H:%M"),
            "tool_calls": m["tool_calls"] or [],
            "token_usage": m["token_usage"] or {},
        }
        for m in msgs
    ]
    return JsonResponse({"messages": data, "title": convo.title})


def chat_send_view(request, conversation_id):
    """Accept a user message, stream the Bedrock response back as SSE events."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)

    try:
        body = json.loads(request.body)
        user_content = body.get("message", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    if not user_content:
        return JsonResponse({"error": "Message cannot be empty"}, status=400)

    ChatMessage.objects.create(conversation=convo, role="user", content=user_content)

    if convo.title == "New Chat":
        convo.title = user_content[:100]
        convo.save(update_fields=["title", "updated_at"])
    else:
        convo.save(update_fields=["updated_at"])

    history = list(convo.messages.order_by("created_at").values("role", "content"))

    chat_config = SystemIntelligenceConfig.load()

    from core.models import AWSCredentialConfig

    effective_model_id = AWSCredentialConfig.load().default_model_id

    def _sse(event, data):
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    def event_stream():
        full_text = ""
        tool_calls = []
        total_usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}

        try:
            for event in invoke_bedrock_stream(history, chat_config=chat_config, model_id=effective_model_id):
                etype = event.get("type")
                if etype == "text":
                    full_text += event["chunk"]
                    yield _sse("text", {"chunk": event["chunk"]})
                elif etype == "tool_call":
                    tool_calls.append(event)
                    yield _sse("tool_call", event)
                elif etype == "usage":
                    total_usage["inputTokens"] += event.get("inputTokens", 0)
                    total_usage["outputTokens"] += event.get("outputTokens", 0)
                    total_usage["totalTokens"] += event.get("totalTokens", 0)
                    yield _sse("usage", total_usage)
                elif etype == "error":
                    yield _sse("error", {"error": event["error"]})
                    return
        except Exception as exc:
            logger.exception("Stream error for conversation %s", conversation_id)
            yield _sse("error", {"error": str(exc)})
            return

        if not full_text:
            full_text = "(empty response)"

        assistant_msg = ChatMessage.objects.create(
            conversation=convo,
            role="assistant",
            content=full_text,
            model_id=effective_model_id,
            tool_calls=_tool_calls_for_storage(tool_calls),
            token_usage=total_usage,
        )

        yield _sse(
            "done",
            {
                "id": str(assistant_msg.id),
                "model_id": effective_model_id,
                "title": convo.title,
                "tool_calls": tool_calls,
                "token_usage": total_usage,
            },
        )

    resp = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    resp["Content-Encoding"] = "identity"
    return resp


def chat_delete_view(request, conversation_id):
    """Delete a conversation."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    deleted, _ = ChatConversation.objects.filter(id=conversation_id, created_by=request.user).delete()

    if not deleted:
        return JsonResponse({"error": "Conversation not found"}, status=404)

    return JsonResponse({"ok": True})


def chat_rename_view(request, conversation_id):
    """Rename a conversation."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)

    try:
        body = json.loads(request.body)
        new_title = body.get("title", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    if not new_title:
        return JsonResponse({"error": "Title cannot be empty"}, status=400)

    convo.title = new_title[:200]
    convo.save(update_fields=["title", "updated_at"])
    return JsonResponse({"ok": True, "title": convo.title})


# ---------------------------------------------------------------------------
# SystemIntelligenceConfig ModelAdmin
# ---------------------------------------------------------------------------


class SystemIntelligenceConfigForm(forms.ModelForm):
    class Meta:
        model = SystemIntelligenceConfig
        fields = "__all__"
        widgets = {
            "system_prompt": UnfoldAdminTextareaWidget(attrs={"rows": 8}),
        }


@admin.register(SystemIntelligenceConfig)
class SystemIntelligenceConfigAdmin(BaseModelAdmin):
    form = SystemIntelligenceConfigForm
    list_display = ("name", "status_badge", "temperature", "max_tokens", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("Model Settings"),
            {
                "fields": ("temperature", "max_tokens"),
                "description": "Amazon Bedrock generation parameters. Model defaults from AWS Credential Config.",
            },
        ),
        (
            _("System Prompt"),
            {
                "fields": ("system_prompt",),
            },
        ),
        (_("Info"), {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = SystemIntelligenceConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active System Intelligence config.')
        return HttpResponseRedirect(reverse("admin:core_systemintelligenceconfig_change", args=[object_id]))

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
