from collections.abc import Iterable

from ..errors import SystemIntelligenceAgentError


def split_history_and_current_message(messages: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    items = list(messages)
    if not items:
        raise SystemIntelligenceAgentError("Message history is empty.")
    current = items[-1]
    if current.get("role") != "user":
        raise SystemIntelligenceAgentError("The latest message must be a user message.")
    user_message = (current.get("content") or "").strip()
    if not user_message:
        raise SystemIntelligenceAgentError("Message cannot be empty.")
    return items[:-1], user_message
