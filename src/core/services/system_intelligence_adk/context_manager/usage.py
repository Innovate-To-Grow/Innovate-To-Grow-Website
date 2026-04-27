from dataclasses import dataclass
from typing import Any

from core.models.base.system_intelligence import ChatMessage

from .messages import serialize_message
from .tokens import estimate_messages_tokens


@dataclass
class PreparedContext:
    messages: list[dict[str, str]]
    usage: dict[str, Any]
    error: str = ""


def base_usage(
    context_window: int,
    compact_threshold: int,
    hard_limit: int,
    system_tokens: int,
    messages: list[ChatMessage],
) -> dict[str, Any]:
    raw_messages = [serialize_message(message) for message in messages]
    raw_tokens = system_tokens + estimate_messages_tokens(raw_messages)
    return {
        "contextWindow": context_window,
        "compactThreshold": compact_threshold,
        "hardLimit": hard_limit,
        "systemTokens": system_tokens,
        "rawTokens": raw_tokens,
        "preparedTokens": 0,
        "rawMessageCount": len(messages),
        "preparedMessageCount": 0,
        "compacted": False,
        "summaryUsed": False,
        "summaryUpdated": False,
        "summaryFailed": False,
        "retainedMessages": 0,
        "summarizedMessages": 0,
        "trimmedMessages": 0,
    }


def context_usage(
    *,
    context_window: int,
    compact_threshold: int,
    hard_limit: int,
    system_tokens: int,
    raw_tokens: int,
    prepared_messages: list[dict[str, str]],
    raw_message_count: int,
    compacted: bool,
    action_tokens: int = 0,
    summary_meta: dict[str, Any] | None = None,
    trim_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary_meta = summary_meta or {}
    trim_meta = trim_meta or {}
    prepared_tokens = system_tokens + estimate_messages_tokens(prepared_messages)
    return {
        "contextWindow": context_window,
        "compactThreshold": compact_threshold,
        "hardLimit": hard_limit,
        "systemTokens": system_tokens,
        "rawTokens": raw_tokens,
        "preparedTokens": prepared_tokens,
        "rawMessageCount": raw_message_count,
        "preparedMessageCount": len(prepared_messages),
        "retainedMessages": trim_meta.get("retained_messages", raw_message_count),
        "summarizedMessages": summary_meta.get("summarized_messages", 0),
        "trimmedMessages": trim_meta.get("trimmed_messages", 0),
        "actionTokens": action_tokens,
        "compacted": compacted,
        "summaryUsed": bool(summary_meta.get("summary_used")),
        "summaryUpdated": bool(summary_meta.get("summary_updated")),
        "summaryFailed": bool(summary_meta.get("summary_failed")),
        "summaryThroughMessageId": summary_meta.get("summary_through_message_id", ""),
    }
