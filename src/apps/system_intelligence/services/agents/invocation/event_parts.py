import json
import uuid
from typing import Any


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
