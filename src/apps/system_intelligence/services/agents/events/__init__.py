import json
import uuid
from typing import Any

from ..errors import format_system_intelligence_error


class StreamState:
    def __init__(self):
        self.streamed_text = ""
        self.pending_tool_calls: dict[str, dict[str, Any]] = {}


def normalize_agent_stream_event(event: Any, state: StreamState) -> list[dict[str, Any]]:
    error = getattr(event, "error", None) or getattr(event, "error_message", None)
    if error:
        return [{"type": "error", "error": format_system_intelligence_error(str(error))}]

    event_type = getattr(event, "type", "")
    if event_type == "raw_response_event":
        return text_delta_events(getattr(event, "data", None), state)
    if event_type != "run_item_stream_event":
        return []

    item = getattr(event, "item", None)
    item_type = getattr(item, "type", "")
    event_name = getattr(event, "name", "")
    if event_name == "tool_called" or item_type == "tool_call_item":
        remember_tool_call(item, state)
        return []
    if event_name == "tool_output" or item_type == "tool_call_output_item":
        return tool_call_events(item, state)
    if event_name == "message_output_created" or item_type == "message_output_item":
        return message_output_events(item, state)
    return []


def text_delta_events(data: Any, state: StreamState) -> list[dict[str, Any]]:
    if getattr(data, "type", "") != "response.output_text.delta":
        return []
    delta = getattr(data, "delta", "") or ""
    if not delta:
        return []
    state.streamed_text += delta
    return [{"type": "text", "chunk": delta}]


def message_output_events(item: Any, state: StreamState) -> list[dict[str, Any]]:
    """Emit the final message text not already delivered via raw streaming deltas.

    The goal is to never DROP assistant text and never DUPLICATE it:

    - Fully streamed already (``streamed_text`` ends with this message): emit nothing.
    - Streamed deltas delivered a leading chunk of this message: emit only the remainder.
    - No overlap (a provider that does not emit ``response.output_text.delta``, or a
      fresh message after a tool call): emit the whole message text.

    The previous implementation used a bare ``removeprefix`` that silently dropped the
    final message whenever it was not a clean prefix-extension of the accumulated
    deltas (e.g. a second message after a tool call, or a re-rendered final).
    """
    text = extract_message_text(item)
    if not text:
        return []
    if state.streamed_text.endswith(text):
        return []
    if state.streamed_text and text.startswith(state.streamed_text):
        remainder = text[len(state.streamed_text) :]
        state.streamed_text += remainder
        return [{"type": "text", "chunk": remainder}]
    state.streamed_text += text
    return [{"type": "text", "chunk": text}]


def remember_tool_call(item: Any, state: StreamState) -> None:
    raw_item = getattr(item, "raw_item", None)
    call_id = tool_call_id(raw_item)
    state.pending_tool_calls[call_id] = {
        "name": tool_call_name(raw_item),
        "input": tool_call_arguments(raw_item),
    }


def tool_call_events(item: Any, state: StreamState) -> list[dict[str, Any]]:
    raw_item = getattr(item, "raw_item", None)
    call_id = tool_call_id(raw_item)
    pending = state.pending_tool_calls.pop(call_id, {})
    output = normalize_tool_output(getattr(item, "output", None))
    events = [
        {
            "type": "tool_call",
            "name": pending.get("name") or tool_call_name(raw_item),
            "input": pending.get("input") or {},
            "result_preview": result_preview(output)[:200],
        }
    ]
    action_request = output.get("action_request") if isinstance(output, dict) else None
    if isinstance(action_request, dict):
        events.append({"type": "action_request", **action_request})
    return events


def tool_call_id(raw_item: Any) -> str:
    if isinstance(raw_item, dict):
        value = raw_item.get("call_id") or raw_item.get("id") or raw_item.get("name")
    else:
        value = getattr(raw_item, "call_id", None) or getattr(raw_item, "id", None) or getattr(raw_item, "name", None)
    return str(value or uuid.uuid4())


def tool_call_name(raw_item: Any) -> str:
    if isinstance(raw_item, dict):
        value = raw_item.get("name")
    else:
        value = getattr(raw_item, "name", None)
    return str(value or "unknown")


def tool_call_arguments(raw_item: Any) -> dict[str, Any]:
    if isinstance(raw_item, dict):
        args = raw_item.get("arguments")
    else:
        args = getattr(raw_item, "arguments", None)
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def normalize_tool_output(output: Any) -> Any:
    if isinstance(output, str):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    return output


def extract_message_text(item: Any) -> str:
    raw_item = getattr(item, "raw_item", None)
    content = raw_item.get("content") if isinstance(raw_item, dict) else getattr(raw_item, "content", None)
    if not content:
        return ""
    parts = []
    for part in content:
        if isinstance(part, dict):
            text = part.get("text")
        else:
            text = getattr(part, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def result_preview(response: Any) -> str:
    if isinstance(response, dict):
        result = response.get("result")
        return result if isinstance(result, str) else json.dumps(response, default=str)
    return response if isinstance(response, str) else str(response)


def usage_event(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    input_tokens = metadata_int(usage, "input_tokens", "inputTokens")
    output_tokens = metadata_int(usage, "output_tokens", "outputTokens")
    total_tokens = metadata_int(usage, "total_tokens", "totalTokens") or input_tokens + output_tokens
    cache_read_tokens = nested_metadata_int(usage, "input_tokens_details", "cached_tokens")
    if not any((input_tokens, output_tokens, total_tokens, cache_read_tokens)):
        return None
    event = {
        "type": "usage",
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
    }
    if cache_read_tokens:
        event["cacheReadInputTokens"] = cache_read_tokens
    return event


def metadata_int(obj: Any, *keys: str) -> int:
    data = obj.model_dump() if hasattr(obj, "model_dump") else obj if isinstance(obj, dict) else {}
    for key in keys:
        value = data.get(key)
        if value is None:
            value = getattr(obj, key, None)
        if isinstance(value, int):
            return value
    return 0


def nested_metadata_int(obj: Any, attr: str, key: str) -> int:
    nested = getattr(obj, attr, None)
    if isinstance(nested, list):
        nested = nested[0] if nested else None
    if isinstance(nested, dict):
        value = nested.get(key)
    else:
        value = getattr(nested, key, None)
    return value if isinstance(value, int) else 0
