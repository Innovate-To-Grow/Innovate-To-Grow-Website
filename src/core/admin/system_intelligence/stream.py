import json

from django.http import JsonResponse, StreamingHttpResponse

from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceConfig,
)
from core.services.system_intelligence_adk import invoke_system_intelligence_stream as _default_stream

from .stream_helpers import _create_assistant_message, _handle_stream_event, _sse, _stream_exception


def _stream_callable():
    import core.admin.system_intelligence as package

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

    ChatMessage.objects.create(conversation=convo, role="user", content=user_content)
    title_updated = convo.title == "New Chat"
    if title_updated:
        convo.title = user_content[:100]
    convo.save(update_fields=["title", "updated_at"] if title_updated else ["updated_at"])

    history = list(convo.messages.order_by("created_at").values("role", "content"))
    chat_config = SystemIntelligenceConfig.load()
    aws_config = AWSCredentialConfig.load()
    model_id = aws_config.default_model_id

    response = StreamingHttpResponse(
        _event_stream(request, convo, history, chat_config, aws_config, model_id),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Content-Encoding"] = "identity"
    return response


def _event_stream(request, convo, history, chat_config, aws_config, model_id):
    full_text = ""
    tool_calls = []
    action_ids = []
    action_requests = []
    total_usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    try:
        for event in _stream_callable()(
            history,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=str(request.user.pk),
            conversation_id=str(convo.pk),
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

    assistant = _create_assistant_message(convo, full_text, model_id, tool_calls, total_usage, action_ids)
    yield _sse(
        "done",
        {
            "id": str(assistant.id),
            "model_id": model_id,
            "title": convo.title,
            "tool_calls": tool_calls,
            "action_requests": action_requests,
            "token_usage": total_usage,
        },
    )
