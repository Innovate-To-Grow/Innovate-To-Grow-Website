import json

from django.http import JsonResponse
from django.utils import timezone

from core.models import AWSCredentialConfig
from system_intelligence.models import (
    ChatConversation,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
)
from system_intelligence.services.adk.context_manager import (
    RECENT_TARGET_TURNS,
    ensure_context_summary,
)

from ..stream import build_stream_response, persist_user_message

COMPACT_MIN_CANDIDATES = 2
TITLE_MAX_LENGTH = 200


def chat_command_view(request, conversation_id):
    """Dispatch a slash-command POSTed from the chat input."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    command = (body.get("command") or "").strip()
    args = (body.get("args") or "").strip()
    handler = COMMAND_HANDLERS.get(command)
    if handler is None:
        return JsonResponse({"error": f"Unknown command: /{command}"}, status=400)
    return handler(request, convo, args)


def _handle_plan(request, convo, args):
    if convo.mode != ChatConversation.MODE_PLAN:
        convo.mode = ChatConversation.MODE_PLAN
        convo.save(update_fields=["mode", "updated_at"])
    if not args:
        return JsonResponse(
            {
                "mode": convo.mode,
                "message": "Plan mode enabled. Describe what you want to plan.",
            }
        )
    persist_user_message(convo, args)
    return build_stream_response(request, convo)


def _handle_exit_plan(_request, convo, _args):
    if convo.mode != ChatConversation.MODE_NORMAL:
        convo.mode = ChatConversation.MODE_NORMAL
        convo.save(update_fields=["mode", "updated_at"])
    return JsonResponse({"mode": convo.mode})


def _handle_compact(request, convo, _args):
    messages = list(convo.messages.order_by("created_at"))
    target_recent_count = RECENT_TARGET_TURNS * 2
    candidates = messages[: max(0, len(messages) - target_recent_count)]
    if len(candidates) < COMPACT_MIN_CANDIDATES:
        return JsonResponse(
            {
                "compacted": False,
                "message": "Not enough older messages to summarize yet.",
            }
        )

    chat_config = SystemIntelligenceConfig.load()
    aws_config = AWSCredentialConfig.load()
    if not aws_config.is_configured:
        return JsonResponse({"error": "AWS credentials are not configured."}, status=400)
    summary_text, meta = ensure_context_summary(
        convo,
        candidates,
        chat_config=chat_config,
        aws_config=aws_config,
        model_id=aws_config.default_model_id,
        user_id=str(request.user.pk),
        force=True,
    )
    return JsonResponse(
        {
            "compacted": True,
            "summary_chars": len(summary_text or ""),
            "messages_summarized": meta.get("summarized_messages", 0),
            "summary_failed": meta.get("summary_failed", False),
        }
    )


def _handle_title(_request, convo, args):
    title = (args or "").strip()
    if not title:
        return JsonResponse(
            {"error": "Usage: /title <new title>"},
            status=400,
        )
    convo.title = title[:TITLE_MAX_LENGTH]
    convo.auto_title = False
    convo.save(update_fields=["title", "auto_title", "updated_at"])
    return JsonResponse({"ok": True, "title": convo.title})


def _handle_retry(request, convo, _args):
    messages = list(convo.messages.order_by("-created_at"))
    if not messages:
        return JsonResponse({"error": "Nothing to retry yet."}, status=400)
    while messages and messages[0].role == "assistant":
        _reject_pending_actions_for_message(messages[0], request.user)
        messages[0].delete()
        messages.pop(0)
    if not messages or messages[0].role != "user":
        return JsonResponse({"error": "No user message to retry."}, status=400)
    return build_stream_response(request, convo)


def _reject_pending_actions_for_message(message, user):
    """Reject pending action requests tied to ``message`` before it is deleted.

    The FK uses on_delete=SET_NULL, so without this step the requests would
    survive as orphaned pending records that leak into pending_action_context_message
    on later turns even though the user can no longer review them.
    """
    now = timezone.now()
    SystemIntelligenceActionRequest.objects.filter(
        assistant_message=message,
        status=SystemIntelligenceActionRequest.STATUS_PENDING,
    ).update(
        status=SystemIntelligenceActionRequest.STATUS_REJECTED,
        reviewed_by=user,
        reviewed_at=now,
        updated_at=now,
    )


COMMAND_HANDLERS = {
    "plan": _handle_plan,
    "exit-plan": _handle_exit_plan,
    "compact": _handle_compact,
    "title": _handle_title,
    "retry": _handle_retry,
}
