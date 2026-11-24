"""The chat stream when the model is called asynchronously: context preparation, provider payloads, heartbeats."""

from contextlib import aclosing

from asgiref.sync import sync_to_async

from apps.system_intelligence.services.agents.context_manager import prepare_conversation_context
from apps.system_intelligence.services.agents.invocation.stream import (
    invoke_system_intelligence_stream_async as _default_async_stream,
)

from .heartbeats import _STREAM_HEARTBEAT, _awaitable_stream, _with_heartbeats
from .helpers import _create_assistant_message, _handle_stream_event, _sse, _stream_exception
from .state import _done_event, _StreamState


def _async_stream_callable():
    import apps.system_intelligence.services.agents as package

    return getattr(package, "_invoke_system_intelligence_stream_async", _default_async_stream)


async def _prepared_context_events(state: _StreamState, request, convo, messages, chat_config, aws_config, model_id):
    """Keep-alive comments while the conversation context is prepared; stores it on ``state.prepared_context``."""
    # Context preparation runs ORM queries (and may save a summary), so it
    # must stay on the request's thread-sensitive executor like the rest of
    # the request's DB work: a default-pool thread would use a separate
    # connection that never sees uncommitted writes and is never closed by
    # Django's request_finished cleanup. Heartbeats still flow meanwhile.
    context_events = _with_heartbeats(
        _awaitable_stream(
            sync_to_async(prepare_conversation_context, thread_sensitive=True)(
                convo,
                messages,
                chat_config=chat_config,
                aws_config=aws_config,
                model_id=model_id,
                user_id=str(request.user.pk),
            )
        )
    )
    try:
        async for prepared_item in context_events:
            if prepared_item is _STREAM_HEARTBEAT:
                yield ": keep-alive\n\n"
            else:
                state.prepared_context = prepared_item
    finally:
        await context_events.aclose()


async def _provider_payloads(
    state: _StreamState, request, convo, prepared_context, chat_config, aws_config, model_id, mode
):
    """SSE payloads for the model's events (and keep-alives); sets ``state.stopped`` when the turn ends early."""
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
                state.full_text,
                state.tool_calls,
                state.action_ids,
                state.action_requests,
                state.total_usage,
            )
            if chunk["stop"]:
                state.stopped = True
                yield chunk["payload"]
                return
            state.full_text = chunk["full_text"]
            if chunk["payload"]:
                yield chunk["payload"]
    finally:
        await provider_events.aclose()


async def _async_event_stream(request, convo, messages, chat_config, aws_config, model_id, *, mode="normal"):
    """Run the native async agent stream used by the production ASGI server."""
    state = _StreamState()
    try:
        yield _sse("start", {"model_id": model_id})
        context_stream = _prepared_context_events(state, request, convo, messages, chat_config, aws_config, model_id)
        async with aclosing(context_stream) as keep_alives:
            async for keep_alive in keep_alives:
                yield keep_alive
        prepared_context = state.prepared_context
        if prepared_context is None:
            raise RuntimeError("Conversation context preparation did not return a result.")
        state.context_usage = prepared_context.usage
        if state.context_usage:
            yield _sse("context", state.context_usage)
        if prepared_context.error:
            yield _sse("error", {"error": prepared_context.error})
            return

        payloads = _provider_payloads(state, request, convo, prepared_context, chat_config, aws_config, model_id, mode)
        async with aclosing(payloads) as provider_payloads:
            async for payload in provider_payloads:
                yield payload
        if state.stopped:
            return
    except Exception as exc:
        yield _stream_exception(convo.id, exc, aws_config, getattr(chat_config, "default_provider", None))
        return

    assistant = await sync_to_async(_create_assistant_message, thread_sensitive=True)(
        convo,
        state.full_text,
        model_id,
        state.tool_calls,
        state.total_usage,
        state.action_ids,
        state.context_usage,
    )
    yield _done_event(
        convo, assistant, model_id, state.tool_calls, state.action_requests, state.total_usage, state.context_usage
    )
