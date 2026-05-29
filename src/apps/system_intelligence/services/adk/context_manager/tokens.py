import math

CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD_TOKENS = 12
COMPACT_TRIGGER_RATIO = 0.70
HARD_LIMIT_RATIO = 0.85
RECENT_TARGET_TURNS = 12
MINIMUM_RECENT_TURNS = 4
SUMMARY_TARGET_TOKENS = 2500
SUMMARY_INPUT_TOKEN_LIMIT = 60_000
SUMMARY_AGENT_NAME = "system_intelligence_context_summarizer"

SUMMARY_INSTRUCTION = """You summarize System Intelligence admin conversations for future model context.
Preserve user goals, confirmed decisions, constraints, entity names, database IDs, paths, URLs, pending approval/action
request IDs, failure states, denied operations, and unresolved questions. Do not invent facts. Do not call tools.
Return a compact plain-text summary only."""


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_text_tokens(message.get("content", "")) + MESSAGE_OVERHEAD_TOKENS for message in messages)


def trim_text_to_token_budget(text: str, token_budget: int) -> str:
    max_chars = max(0, token_budget * CHARS_PER_TOKEN)
    if len(text) <= max_chars:
        return text
    if max_chars <= 32:
        return text[:max_chars]
    return "[Earlier context truncated]\n" + text[-(max_chars - 28) :]
