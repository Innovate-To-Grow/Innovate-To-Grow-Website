import json
import logging
import re

from system_intelligence.models import ChatMessage, SystemIntelligenceActionRequest
from system_intelligence.services.adk import format_system_intelligence_error
from system_intelligence.services.adk.errors import (
    exception_chain_message,
    is_bedrock_connectivity_error,
)

logger = logging.getLogger(__name__)

_AWS_REGION_RE = re.compile(r"^[a-z]{2,4}-[a-z]+-\d+$")


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


_GENERIC_STREAM_ERROR = "The assistant could not complete this turn. See server logs for details."


def _stream_exception(conversation_id, exc, aws_config):
    """Build a user-facing SSE error from a controlled string template.

    The exception text is logged but never copied into the response. For
    recognised Bedrock connectivity failures we substitute a regex-validated
    region from aws_config. Anything else gets a generic message.
    """
    chain = exception_chain_message(exc)
    if is_bedrock_connectivity_error(chain):
        region_raw = (getattr(aws_config, "default_region", None) or "").strip()
        region = region_raw if _AWS_REGION_RE.fullmatch(region_raw) else "the configured region"
        logger.warning(
            "Stream provider connectivity failed for conversation %s in region %s",
            conversation_id,
            region,
        )
        message = (
            f"Unable to reach AWS Bedrock Runtime in {region}. "
            "Check network/DNS connectivity for the server and try again."
        )
    else:
        logger.exception("Stream error for conversation %s", conversation_id)
        message = _GENERIC_STREAM_ERROR
    return _sse("error", {"error": message})


def _create_assistant_message(convo, full_text, model_id, tool_calls, total_usage, action_ids, context_usage=None):
    assistant = ChatMessage.objects.create(
        conversation=convo,
        role="assistant",
        content=full_text or "(empty response)",
        model_id=model_id,
        tool_calls=_tool_calls_for_storage(tool_calls),
        token_usage=total_usage,
        context_usage=context_usage or {},
    )
    SystemIntelligenceActionRequest.objects.filter(
        id__in=[action_id for action_id in action_ids if action_id],
        conversation=convo,
        assistant_message__isnull=True,
    ).update(assistant_message=assistant)
    return assistant


def _result(full_text, payload):
    return {"full_text": full_text, "payload": payload, "stop": False}
