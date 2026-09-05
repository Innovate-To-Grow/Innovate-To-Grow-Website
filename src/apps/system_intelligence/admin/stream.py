import asyncio
import json

from asgiref.sync import sync_to_async
from django.core.exceptions import PermissionDenied
from django.core.handlers.asgi import ASGIRequest
from django.http import JsonResponse, StreamingHttpResponse

from apps.core.models import AWSCredentialConfig
from apps.core.utils.access import user_can_access_app
from apps.system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.agents import invoke_system_intelligence_stream as _default_stream
from apps.system_intelligence.services.agents.context_manager import prepare_conversation_context
from apps.system_intelligence.services.agents.stream import (
    invoke_system_intelligence_stream_async as _default_async_stream,
)

from .stream_helpers import _create_assistant_message, _handle_stream_event, _sse, _stream_exception

USER_MESSAGE_MAX_CHARS = 20_000
STREAM_HEARTBEAT_SECONDS = 15
_STREAM_END = object()
_STREAM_HEARTBEAT = object()


def _stream_callable():
    import apps.system_intelligence.admin as package

    return getattr(package, "invoke_system_intelligence_stream", _default_stream)


def _async_stream_callable():
    import apps.system_intelligence.services.agents as package

    return getattr(package, "_invoke_system_intelligence_stream_async", _default_async_stream)


def chat_send_view(request, conversation_id):
    """Accept a user message, stream the Agent/Bedrock response back as SSE."""
    # admin_view only enforces is_staff; re-check the per-app model here.
    if not user_can_access_app(request.user, "system_intelligence"):
        raise PermissionDenied("You do not have permission to access System Intelligence.")
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


async def _with_heartbeats(event_stream, *, heartbeat_seconds=STREAM_HEARTBEAT_SECONDS):
    """Yield async provider events while keeping idle SSE connections alive."""
    iterator = aiter(event_stream)
    pending_item = None
    try:
        while True:
            pending_item = asyncio.create_task(anext(iterator, _STREAM_END))
            while True:
                done, _pending = await asyncio.wait({pending_item}, timeout=heartbeat_seconds)
                if done:
                    # Calling result() preserves provider exceptions (including
                    # TimeoutError) instead of confusing them with a heartbeat.
                    item = pending_item.result()
                    break
                yield _STREAM_HEARTBEAT
            pending_item = None
            if item is _STREAM_END:
                return
            yield item
    finally:
        if pending_item is not None:
            if not pending_item.done():
                pending_item.cancel()
            await asyncio.gather(pending_item, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


async def _awaitable_stream(awaitable):
    """Adapt one awaitable so long setup work can use the heartbeat wrapper."""
    yield await awaitable


async def _async_event_stream(request, convo, messages, chat_config, aws_config, model_id, *, mode="normal"):
    """Run the native async agent stream used by the production ASGI server."""
    full_text = ""
    tool_calls = []
    action_ids = []
    action_requests = []
    total_usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    context_usage = {}
    try:
        yield _sse("start", {"model_id": model_id})
        context_events = _with_heartbeats(
            _awaitable_stream(
                sync_to_async(prepare_conversation_context, thread_sensitive=False)(
                    convo,
                    messages,
                    chat_config=chat_config,
                    aws_config=aws_config,
                    model_id=model_id,
                    user_id=str(request.user.pk),
                )
            )
        )
        prepared_context = None
        try:
            async for prepared_item in context_events:
                if prepared_item is _STREAM_HEARTBEAT:
                    yield ": keep-alive\n\n"
                else:
                    prepared_context = prepared_item
        finally:
            await context_events.aclose()
        if prepared_context is None:
            raise RuntimeError("Conversation context preparation did not return a result.")
        context_usage = prepared_context.usage
        if context_usage:
            yield _sse("context", context_usage)
        if prepared_context.error:
            yield _sse("error", {"error": prepared_context.error})
            return

        provider_events = _with_heartbeats(
            _async_stream_callable()(
                prepared_context.messages,
                chat_config=chat_config,
                aws_config=aws_config,
                model_id=model_id,
                user_id=str(request.user.pk),
                conversation_id=str(convo.pk),
                mode=mode,
            )
        )
        try:
            async for event in provider_events:
                if event is _STREAM_HEARTBEAT:
                    yield ": keep-alive\n\n"
                    continue
                chunk = _handle_stream_event(
                    event,
                    aws_config,
                    full_text,
                    tool_calls,
                    action_ids,
                    action_requests,
                    total_usage,
                )
                if chunk["stop"]:
                    yield chunk["payload"]
                    return
                full_text = chunk["full_text"]
                if chunk["payload"]:
                    yield chunk["payload"]
        finally:
            await provider_events.aclose()
    except Exception as exc:
        yield _stream_exception(convo.id, exc, aws_config)
        return

    assistant = await sync_to_async(_create_assistant_message, thread_sensitive=True)(
        convo,
        full_text,
        model_id,
        tool_calls,
        total_usage,
        action_ids,
        context_usage,
    )
    yield _done_event(convo, assistant, model_id, tool_calls, action_requests, total_usage, context_usage)


def _done_event(convo, assistant, model_id, tool_calls, action_requests, total_usage, context_usage):
    return _sse(
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


def _event_stream(request, convo, messages, chat_config, aws_config, model_id, *, mode="normal"):
    full_text = ""
    tool_calls = []
    action_ids = []
    action_requests = []
    total_usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    context_usage = {}
    try:
        # Flush response headers and a first SSE frame before context/model work.
        yield _sse("start", {"model_id": model_id})
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
    yield _done_event(convo, assistant, model_id, tool_calls, action_requests, total_usage, context_usage)
