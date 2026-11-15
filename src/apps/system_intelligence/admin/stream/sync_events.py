"""The chat stream when the model is called synchronously (one thread per stream)."""

from apps.system_intelligence.services.agents import invoke_system_intelligence_stream as _default_stream
from apps.system_intelligence.services.agents.context_manager import prepare_conversation_context

from .helpers import _create_assistant_message, _handle_stream_event, _sse, _stream_exception
from .state import _done_event


def _stream_callable():
    import apps.system_intelligence.admin as package

    return getattr(package, "invoke_system_intelligence_stream", _default_stream)


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
