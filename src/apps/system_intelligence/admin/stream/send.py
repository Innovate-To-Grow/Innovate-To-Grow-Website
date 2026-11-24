"""Sending a chat message: the send view, the stored user message, and the streaming response."""

import json

from django.core.exceptions import PermissionDenied
from django.core.handlers.asgi import ASGIRequest
from django.http import JsonResponse, StreamingHttpResponse

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.actions.engine.tool_access import has_chat_grants

from .async_events import _async_event_stream
from .sync_events import _event_stream

USER_MESSAGE_MAX_CHARS = 20_000


def chat_send_view(request, conversation_id):
    """Accept a user message, stream the Agent/Bedrock response back as SSE."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)
    refused = conversation_turn_refusal(request.user, convo)
    if refused is not None:
        return refused
    try:
        user_content = json.loads(request.body).get("message", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)
    if not user_content:
        return JsonResponse({"error": "Message cannot be empty"}, status=400)
    if len(user_content) > USER_MESSAGE_MAX_CHARS:
        return JsonResponse(
            {"error": f"Message exceeds {USER_MESSAGE_MAX_CHARS:,} characters."},
            status=400,
        )

    persist_user_message(convo, user_content)
    return build_stream_response(request, convo)


def conversation_turn_refusal(user, convo):
    if convo.required_tool_apps is None:
        return JsonResponse({"error": "This conversation is archived. Start a new chat to continue."}, status=409)
    if not has_chat_grants(user, convo.required_tool_apps):
        raise PermissionDenied("You do not have access to this conversation.")
    return None


def persist_user_message(convo, user_content):
    """Persist a user message and auto-rename the conversation on first turn.

    The auto-rename runs only while ``convo.auto_title`` is true, which the
    rename view clears as soon as a human picks a title. That way a user who
    deliberately renames a conversation back to "New Chat" doesn't get their
    next message silently overwriting the title.
    """
    ChatMessage.objects.create(conversation=convo, role="user", content=user_content)
    if convo.auto_title:
        convo.title = user_content[:100]
        convo.auto_title = False
        convo.save(update_fields=["title", "auto_title", "updated_at"])
    else:
        convo.save(update_fields=["updated_at"])


def build_stream_response(request, convo):
    """Stream the next assistant turn for ``convo``, honoring its current mode."""
    messages = list(convo.messages.prefetch_related("action_requests").order_by("created_at"))
    chat_config = SystemIntelligenceConfig.load()
    aws_config = AWSCredentialConfig.load()
    model_id = chat_config.default_model_id

    if isinstance(request, ASGIRequest):
        # Production runs on Uvicorn. Use the native async agent stream so
        # Django can forward each frame without buffering the entire turn and
        # can cancel the upstream model call when the client disconnects.
        event_stream = _async_event_stream(
            request,
            convo,
            messages,
            chat_config,
            aws_config,
            model_id,
            mode=convo.mode,
        )
    else:
        event_stream = _event_stream(request, convo, messages, chat_config, aws_config, model_id, mode=convo.mode)
    response = StreamingHttpResponse(event_stream, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Content-Encoding"] = "identity"
    return response
