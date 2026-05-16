import json

from django.http import JsonResponse, StreamingHttpResponse

from core.models import AWSCredentialConfig
from system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceConfig,
)
from system_intelligence.services.adk import invoke_system_intelligence_stream as _default_stream
from system_intelligence.services.adk.context_manager import prepare_conversation_context

from .stream_helpers import _create_assistant_message, _handle_stream_event, _sse, _stream_exception

USER_MESSAGE_MAX_CHARS = 20_000


def _stream_callable():
    import system_intelligence.admin as package

    return getattr(package, "invoke_system_intelligence_stream", _default_stream)


def chat_send_view(request, conversation_id):
    """Accept a user message, stream the ADK/Bedrock response back as SSE."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)
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
    model_id = aws_config.default_model_id

    response = StreamingHttpResponse(
        _event_stream(request, convo, messages, chat_config, aws_config, model_id, mode=convo.mode),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Content-Encoding"] = "identity"
    return response


def _event_stream(request, convo, messages, chat_config, aws_config, model_id, *, mode="normal"):
    full_text = ""
    tool_calls = []
    action_ids = []
    action_requests = []
    total_usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    context_usage = {}
    try:
        prepared_context = prepare_conversation_context(
            convo,
            messages,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=str(request.user.pk),
        )
        context_usage = prepared_context.usage
        if context_usage:
            yield _sse("context", context_usage)
        if prepared_context.error:
            yield _sse("error", {"error": prepared_context.error})
            return
        for event in _stream_callable()(
            prepared_context.messages,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=str(request.user.pk),
            conversation_id=str(convo.pk),
            mode=mode,
        ):
            chunk = _handle_stream_event(
                event, aws_config, full_text, tool_calls, action_ids, action_requests, total_usage
            )
            if chunk["stop"]:
                yield chunk["payload"]
                return
            full_text = chunk["full_text"]
            if chunk["payload"]:
                yield chunk["payload"]
    except Exception as exc:
        yield _stream_exception(convo.id, exc, aws_config)
        return

    assistant = _create_assistant_message(
        convo, full_text, model_id, tool_calls, total_usage, action_ids, context_usage
    )
    yield _sse(
        "done",
        {
            "id": str(assistant.id),
            "model_id": model_id,
            "title": convo.title,
            "tool_calls": tool_calls,
            "action_requests": action_requests,
            "token_usage": total_usage,
            "context_usage": context_usage,
        },
    )
