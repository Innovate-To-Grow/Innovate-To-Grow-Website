import json
import uuid
from typing import Any

from google.adk.events import Event

from ..errors import format_system_intelligence_error


class StreamState:
    def __init__(self):
        self.streamed_text = ""
        self.pending_tool_calls: dict[str, dict[str, Any]] = {}


def normalize_adk_event(event: Event, state: StreamState) -> list[dict[str, Any]]:
    normalized = []
    error_message = getattr(event, "error_message", None)
    if error_message:
        return [{"type": "error", "error": format_system_intelligence_error(str(error_message))}]
    for function_call in event.get_function_calls():
        key = tool_event_key(function_call)
        state.pending_tool_calls[key] = {
            "name": getattr(function_call, "name", None) or "unknown",
            "input": getattr(function_call, "args", None) or {},
        }
    for function_response in event.get_function_responses():
        normalized.extend(tool_call_events(function_response, state))
    normalized.extend(text_events(event, state))
    usage = usage_event(getattr(event, "usage_metadata", None))
    if usage:
        normalized.append(usage)
    return normalized


def text_events(event: Event, state: StreamState) -> list[dict[str, Any]]:
    text = extract_text(event)
    if not text:
        return []
    if event.partial:
        state.streamed_text += text
        return [{"type": "text", "chunk": text}]
    if not state.streamed_text and not event.get_function_calls() and not event.get_function_responses():
        return [{"type": "text", "chunk": text}]
    if event.get_function_calls() or event.get_function_responses():
        return []
    suffix = text.removeprefix(state.streamed_text)
    if suffix != text and suffix:
        state.streamed_text += suffix
        return [{"type": "text", "chunk": suffix}]
    if text != state.streamed_text:
        state.streamed_text += text
        return [{"type": "text", "chunk": text}]
    return []


def tool_call_events(function_response, state: StreamState) -> list[dict[str, Any]]:
    key = tool_event_key(function_response)
    pending = state.pending_tool_calls.pop(key, {})
    response = getattr(function_response, "response", None) or {}
    events = [
        {
            "type": "tool_call",
            "name": getattr(function_response, "name", None) or pending.get("name") or "unknown",
            "input": pending.get("input") or {},
            "result_preview": result_preview(response)[:200],
        }
    ]
    action_request = response.get("action_request") if isinstance(response, dict) else None
    if isinstance(action_request, dict):
        events.append({"type": "action_request", **action_request})
    return events


def tool_event_key(value) -> str:
    return str(getattr(value, "id", None) or getattr(value, "name", None) or uuid.uuid4())


def extract_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(getattr(part, "text", None) or "" for part in event.content.parts)


def result_preview(response: Any) -> str:
    if isinstance(response, dict):
        result = response.get("result")
        return result if isinstance(result, str) else json.dumps(response, default=str)
    return response if isinstance(response, str) else str(response)


def usage_event(usage_metadata: Any) -> dict[str, Any] | None:
    if usage_metadata is None:
        return None
    data = usage_metadata.model_dump() if hasattr(usage_metadata, "model_dump") else {}
    input_tokens = metadata_int(data, usage_metadata, "prompt_token_count", "promptTokenCount")
    output_tokens = metadata_int(data, usage_metadata, "candidates_token_count", "candidatesTokenCount")
    total_tokens = (
        metadata_int(data, usage_metadata, "total_token_count", "totalTokenCount") or input_tokens + output_tokens
    )
    if not any((input_tokens, output_tokens, total_tokens)):
        return None
    return {"type": "usage", "inputTokens": input_tokens, "outputTokens": output_tokens, "totalTokens": total_tokens}


def metadata_int(data: dict[str, Any], obj: Any, *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if value is None:
            value = getattr(obj, key, None)
        if isinstance(value, int):
            return value
    return 0
