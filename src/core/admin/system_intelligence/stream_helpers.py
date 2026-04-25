import json
import logging

from core.models.base.system_intelligence import ChatMessage, SystemIntelligenceActionRequest
from core.services.system_intelligence_adk import format_system_intelligence_error

logger = logging.getLogger(__name__)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _tool_calls_for_storage(stream_events):
    """Normalize streamed tool_call dicts for JSONField."""
    out = []
    for event in stream_events:
        if not isinstance(event, dict):
            continue
        tool_input = event.get("input")
        if tool_input is not None and not isinstance(tool_input, dict):
            tool_input = {}
        out.append(
            {
                "name": event.get("name", "unknown"),
                "input": tool_input or {},
                "result_preview": event.get("result_preview") or "",
            }
        )
    return out


def _handle_stream_event(event, aws_config, full_text, tool_calls, action_ids, action_requests, total_usage):
    etype = event.get("type")
    if etype == "text":
        full_text += event["chunk"]
        return _result(full_text, _sse("text", {"chunk": event["chunk"]}))
    if etype == "tool_call":
        tool_calls.append(event)
        return _result(full_text, _sse("tool_call", event))
    if etype == "action_request":
        action_ids.append(event.get("id"))
        action_requests.append(event)
        return _result(full_text, _sse("action_request", event))
    if etype == "usage":
        total_usage["inputTokens"] += event.get("inputTokens", 0)
        total_usage["outputTokens"] += event.get("outputTokens", 0)
        total_usage["totalTokens"] += event.get("totalTokens", 0)
        return _result(full_text, _sse("usage", total_usage))
    if etype == "error":
        error = format_system_intelligence_error(event["error"], aws_config=aws_config)
        return {"full_text": full_text, "payload": _sse("error", {"error": error}), "stop": True}
    return _result(full_text, "")


def _stream_exception(conversation_id, exc, aws_config):
    formatted = format_system_intelligence_error(exc, aws_config=aws_config)
    if formatted != str(exc):
        logger.warning("Stream provider connectivity failed for conversation %s: %s", conversation_id, formatted)
    else:
        logger.exception("Stream error for conversation %s", conversation_id)
    return _sse("error", {"error": formatted})


def _create_assistant_message(convo, full_text, model_id, tool_calls, total_usage, action_ids):
    assistant = ChatMessage.objects.create(
        conversation=convo,
        role="assistant",
        content=full_text or "(empty response)",
        model_id=model_id,
        tool_calls=_tool_calls_for_storage(tool_calls),
        token_usage=total_usage,
    )
    SystemIntelligenceActionRequest.objects.filter(
        id__in=[action_id for action_id in action_ids if action_id],
        conversation=convo,
        assistant_message__isnull=True,
    ).update(assistant_message=assistant)
    return assistant


def _result(full_text, payload):
    return {"full_text": full_text, "payload": payload, "stop": False}
