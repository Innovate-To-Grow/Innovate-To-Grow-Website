import math
from typing import Any

from core.models import AWSCredentialConfig
from system_intelligence.models import ChatConversation, ChatMessage, SystemIntelligenceConfig

from ..constants import APPROVAL_INSTRUCTION
from ..context_window import estimate_context_window
from .limits import enforce_hard_limit
from .messages import pending_action_context_message, serialize_message, summary_context_message
from .summary import ensure_context_summary
from .tokens import (
    COMPACT_TRIGGER_RATIO,
    HARD_LIMIT_RATIO,
    MINIMUM_RECENT_TURNS,
    RECENT_TARGET_TURNS,
    estimate_messages_tokens,
    estimate_text_tokens,
)
from .usage import PreparedContext, base_usage, context_usage


def prepare_conversation_context(
    conversation: ChatConversation,
    messages: list[ChatMessage],
    *,
    chat_config: SystemIntelligenceConfig,
    aws_config: AWSCredentialConfig,
    model_id: str,
    user_id: str,
) -> PreparedContext:
    """Build the bounded message history that should be seeded into the ADK session."""
    messages = list(messages)
    if not messages:
        return PreparedContext([], {}, "Message history is empty.")
    current_message = messages[-1]
    if current_message.role != "user":
        return PreparedContext([], {}, "The latest message must be a user message.")

    context_window = estimate_context_window(model_id)
    compact_threshold = math.floor(context_window * COMPACT_TRIGGER_RATIO)
    hard_limit = math.floor(context_window * HARD_LIMIT_RATIO)
    system_tokens = estimate_text_tokens((chat_config.system_prompt or "") + APPROVAL_INSTRUCTION)
    current_tokens = estimate_messages_tokens([serialize_message(current_message)])
    if system_tokens + current_tokens > hard_limit:
        return PreparedContext(
            [],
            base_usage(context_window, compact_threshold, hard_limit, system_tokens, messages),
            "The current message is too large for the configured model context window.",
        )

    serialized_all = [serialize_message(message) for message in messages]
    raw_tokens = system_tokens + estimate_messages_tokens(serialized_all)
    action_message = pending_action_context_message(conversation)
    action_tokens = estimate_messages_tokens([action_message]) if action_message else 0
    should_compact = raw_tokens + action_tokens > compact_threshold

    if not should_compact:
        prepared_messages = ([action_message] if action_message else []) + serialized_all
        return PreparedContext(
            prepared_messages,
            _usage(
                context_window,
                compact_threshold,
                hard_limit,
                system_tokens,
                raw_tokens,
                prepared_messages,
                messages,
                action_tokens,
            ),
        )

    previous_messages = messages[:-1]
    recent_messages = previous_messages[-RECENT_TARGET_TURNS * 2 :]
    compact_candidates = previous_messages[: max(0, len(previous_messages) - len(recent_messages))]
    summary_text, summary_meta = ensure_context_summary(
        conversation,
        compact_candidates,
        chat_config=chat_config,
        aws_config=aws_config,
        model_id=model_id,
        user_id=user_id,
    )
    summary_message = summary_context_message(summary_text) if summary_text else None
    prepared_messages, trim_meta = enforce_hard_limit(
        summary_message=summary_message,
        action_message=action_message,
        recent_messages=[serialize_message(message) for message in recent_messages],
        current_message=serialize_message(current_message),
        system_tokens=system_tokens,
        hard_limit=hard_limit,
        minimum_recent_count=MINIMUM_RECENT_TURNS * 2,
    )
    usage = _usage(
        context_window,
        compact_threshold,
        hard_limit,
        system_tokens,
        raw_tokens,
        prepared_messages,
        messages,
        action_tokens,
        summary_meta=summary_meta,
        trim_meta=trim_meta,
        compacted=True,
    )
    return PreparedContext(prepared_messages, usage, trim_meta["error"])


def _usage(
    context_window: int,
    compact_threshold: int,
    hard_limit: int,
    system_tokens: int,
    raw_tokens: int,
    prepared_messages: list[dict[str, str]],
    messages: list[ChatMessage],
    action_tokens: int,
    *,
    compacted: bool = False,
    summary_meta: dict[str, Any] | None = None,
    trim_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return context_usage(
        context_window=context_window,
        compact_threshold=compact_threshold,
        hard_limit=hard_limit,
        system_tokens=system_tokens,
        raw_tokens=raw_tokens,
        prepared_messages=prepared_messages,
        raw_message_count=len(messages),
        compacted=compacted,
        action_tokens=action_tokens,
        summary_meta=summary_meta,
        trim_meta=trim_meta,
    )
