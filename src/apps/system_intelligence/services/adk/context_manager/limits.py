from typing import Any

from .tokens import MESSAGE_OVERHEAD_TOKENS, estimate_messages_tokens, trim_text_to_token_budget


def enforce_hard_limit(
    *,
    summary_message: dict[str, str] | None,
    action_message: dict[str, str] | None,
    recent_messages: list[dict[str, str]],
    current_message: dict[str, str],
    system_tokens: int,
    hard_limit: int,
    minimum_recent_count: int,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    trimmed_messages = 0
    working_recent = list(recent_messages)
    prepared = combine_prepared_messages(summary_message, action_message, working_recent, current_message)
    while (
        system_tokens + estimate_messages_tokens(prepared) > hard_limit and len(working_recent) > minimum_recent_count
    ):
        working_recent.pop(0)
        trimmed_messages += 1
        prepared = combine_prepared_messages(summary_message, action_message, working_recent, current_message)

    if system_tokens + estimate_messages_tokens(prepared) > hard_limit and summary_message:
        reserved_without_summary = combine_prepared_messages(None, action_message, working_recent, current_message)
        available_summary_tokens = max(
            200,
            hard_limit - system_tokens - estimate_messages_tokens(reserved_without_summary) - MESSAGE_OVERHEAD_TOKENS,
        )
        summary_message = {
            **summary_message,
            "content": trim_text_to_token_budget(summary_message["content"], available_summary_tokens),
        }
        prepared = combine_prepared_messages(summary_message, action_message, working_recent, current_message)

    if system_tokens + estimate_messages_tokens(prepared) > hard_limit and action_message:
        action_message = {**action_message, "content": trim_text_to_token_budget(action_message["content"], 1000)}
        prepared = combine_prepared_messages(summary_message, action_message, working_recent, current_message)

    error = ""
    if system_tokens + estimate_messages_tokens(prepared) > hard_limit:
        error = "The required recent conversation context is too large for the configured model context window."

    return prepared, {
        "trimmed_messages": trimmed_messages,
        "retained_messages": len(working_recent) + 1,
        "error": error,
    }


def combine_prepared_messages(
    summary_message: dict[str, str] | None,
    action_message: dict[str, str] | None,
    recent_messages: list[dict[str, str]],
    current_message: dict[str, str],
) -> list[dict[str, str]]:
    prepared = []
    if summary_message:
        prepared.append(summary_message)
    if action_message:
        prepared.append(action_message)
    prepared.extend(recent_messages)
    prepared.append(current_message)
    return prepared
