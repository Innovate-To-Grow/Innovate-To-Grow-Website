import asyncio
import logging
import math
import uuid
from dataclasses import dataclass
from typing import Any

from django.utils import timezone
from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
)

from .constants import APP_NAME, APPROVAL_INSTRUCTION
from .context_window import estimate_context_window
from .events import StreamState, normalize_adk_event
from .litellm import build_lite_llm_model

logger = logging.getLogger(__name__)

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


@dataclass
class PreparedContext:
    messages: list[dict[str, str]]
    usage: dict[str, Any]
    error: str = ""


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
        usage = context_usage(
            context_window=context_window,
            compact_threshold=compact_threshold,
            hard_limit=hard_limit,
            system_tokens=system_tokens,
            raw_tokens=raw_tokens,
            prepared_messages=prepared_messages,
            raw_message_count=len(messages),
            compacted=False,
            action_tokens=action_tokens,
        )
        return PreparedContext(prepared_messages, usage)

    previous_messages = messages[:-1]
    target_recent_count = RECENT_TARGET_TURNS * 2
    minimum_recent_count = MINIMUM_RECENT_TURNS * 2
    recent_messages = previous_messages[-target_recent_count:]
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
        minimum_recent_count=minimum_recent_count,
    )
    if trim_meta["error"]:
        usage = context_usage(
            context_window=context_window,
            compact_threshold=compact_threshold,
            hard_limit=hard_limit,
            system_tokens=system_tokens,
            raw_tokens=raw_tokens,
            prepared_messages=prepared_messages,
            raw_message_count=len(messages),
            compacted=True,
            action_tokens=action_tokens,
            summary_meta=summary_meta,
            trim_meta=trim_meta,
        )
        return PreparedContext(prepared_messages, usage, trim_meta["error"])

    usage = context_usage(
        context_window=context_window,
        compact_threshold=compact_threshold,
        hard_limit=hard_limit,
        system_tokens=system_tokens,
        raw_tokens=raw_tokens,
        prepared_messages=prepared_messages,
        raw_message_count=len(messages),
        compacted=True,
        action_tokens=action_tokens,
        summary_meta=summary_meta,
        trim_meta=trim_meta,
    )
    return PreparedContext(prepared_messages, usage)


def serialize_message(message: ChatMessage) -> dict[str, str]:
    return {"role": message.role, "content": message.content or ""}


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_text_tokens(message.get("content", "")) + MESSAGE_OVERHEAD_TOKENS for message in messages)


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


def ensure_context_summary(
    conversation: ChatConversation,
    compact_candidates: list[ChatMessage],
    *,
    chat_config: SystemIntelligenceConfig,
    aws_config: AWSCredentialConfig,
    model_id: str,
    user_id: str,
    force: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Build (or refresh) the rolling summary for ``conversation``.

    When ``force`` is False, the function is a no-op if there's nothing new to
    summarize. When True (used by the manual ``/compact`` command), it always
    re-runs the summarizer over any unsummarized candidates so the admin sees
    progress.
    """
    existing_summary = (conversation.context_summary or "").strip()
    meta: dict[str, Any] = {
        "summary_used": bool(existing_summary),
        "summary_updated": False,
        "summary_failed": False,
        "summarized_messages": 0,
        "summary_through_message_id": str(conversation.context_summary_through_message_id or ""),
    }
    if not compact_candidates:
        return existing_summary, meta

    new_candidates = unsummarized_candidates(conversation, compact_candidates)
    if not new_candidates and not force:
        meta["summary_used"] = bool(existing_summary)
        return existing_summary, meta
    if not new_candidates:
        new_candidates = compact_candidates

    source_text = trim_text_to_token_budget(format_messages_for_summary(new_candidates), SUMMARY_INPUT_TOKEN_LIMIT)
    try:
        summary_text = summarize_context(
            existing_summary=existing_summary,
            new_context=source_text,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=user_id,
        )
    except Exception:
        logger.exception("System Intelligence context summarization failed for conversation %s", conversation.pk)
        summary_text = fallback_context_summary(existing_summary, source_text)
        meta["summary_failed"] = True

    through_message = compact_candidates[-1]
    conversation.context_summary = trim_text_to_token_budget(summary_text, SUMMARY_TARGET_TOKENS)
    conversation.context_summary_updated_at = timezone.now()
    conversation.context_summary_through_message = through_message
    conversation.save(
        update_fields=[
            "context_summary",
            "context_summary_updated_at",
            "context_summary_through_message",
            "updated_at",
        ]
    )
    meta.update(
        {
            "summary_used": bool(conversation.context_summary),
            "summary_updated": True,
            "summarized_messages": len(new_candidates),
            "summary_through_message_id": str(through_message.pk),
        }
    )
    return conversation.context_summary, meta


def unsummarized_candidates(conversation: ChatConversation, compact_candidates: list[ChatMessage]) -> list[ChatMessage]:
    existing_summary = (conversation.context_summary or "").strip()
    through_id = conversation.context_summary_through_message_id
    if not existing_summary or not through_id:
        return compact_candidates
    for index, message in enumerate(compact_candidates):
        if message.pk == through_id:
            return compact_candidates[index + 1 :]
    return compact_candidates


def summarize_context(
    *,
    existing_summary: str,
    new_context: str,
    chat_config: SystemIntelligenceConfig,
    aws_config: AWSCredentialConfig,
    model_id: str,
    user_id: str,
) -> str:
    return asyncio.run(
        summarize_context_async(
            existing_summary=existing_summary,
            new_context=new_context,
            chat_config=chat_config,
            aws_config=aws_config,
            model_id=model_id,
            user_id=user_id,
        )
    )


async def summarize_context_async(
    *,
    existing_summary: str,
    new_context: str,
    chat_config: SystemIntelligenceConfig,
    aws_config: AWSCredentialConfig,
    model_id: str,
    user_id: str,
) -> str:
    model = build_lite_llm_model(aws_config=aws_config, model_id=model_id)
    agent = LlmAgent(
        name=SUMMARY_AGENT_NAME,
        description="Summarizes older System Intelligence chat context.",
        model=model,
        instruction=SUMMARY_INSTRUCTION,
        tools=[],
        generate_content_config=types.GenerateContentConfig(maxOutputTokens=SUMMARY_TARGET_TOKENS),
    )
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id or "admin",
        session_id=f"si-summary-{uuid.uuid4()}",
    )
    prompt = summary_prompt(existing_summary, new_context, chat_config)
    state = StreamState()
    response_parts = []
    async for event in runner.run_async(
        user_id=user_id or "admin",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
        run_config=RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=1),
    ):
        for normalized in normalize_adk_event(event, state):
            if normalized.get("type") == "text":
                response_parts.append(normalized["chunk"])
    summary = "".join(response_parts).strip()
    if not summary:
        raise ValueError("Context summarizer returned an empty response.")
    return summary


def summary_prompt(existing_summary: str, new_context: str, chat_config: SystemIntelligenceConfig) -> str:
    system_note = (chat_config.system_prompt or "").strip()
    return (
        "Update the rolling context summary for an administrative AI chat.\n\n"
        f"System prompt context:\n{system_note[:2000]}\n\n"
        f"Existing summary:\n{existing_summary or '(none)'}\n\n"
        f"New conversation messages to incorporate:\n{new_context}\n\n"
        "Return the updated summary. Keep it compact but preserve exact IDs, paths, approval/action IDs, "
        "model/tool constraints, user decisions, and unresolved tasks."
    )


def format_messages_for_summary(messages: list[ChatMessage]) -> str:
    chunks = []
    for message in messages:
        created_at = message.created_at.isoformat() if message.created_at else ""
        chunks.append(f"[{message.role} {message.pk} {created_at}]\n{message.content or ''}".strip())
        for action in list(getattr(message, "action_requests", []).all()):
            chunks.append(
                "Action request "
                f"{action.id}: {action.title} status={action.status} target={action.target_app_label}."
                f"{action.target_model}:{action.target_pk} summary={action.summary}"
            )
    return "\n\n".join(chunks)


def fallback_context_summary(existing_summary: str, new_context: str) -> str:
    combined = "\n\n".join(part for part in [existing_summary.strip(), new_context.strip()] if part)
    return trim_text_to_token_budget(combined, SUMMARY_TARGET_TOKENS)


def trim_text_to_token_budget(text: str, token_budget: int) -> str:
    max_chars = max(0, token_budget * CHARS_PER_TOKEN)
    if len(text) <= max_chars:
        return text
    if max_chars <= 32:
        return text[:max_chars]
    return "[Earlier context truncated]\n" + text[-(max_chars - 28) :]


def pending_action_context_message(conversation: ChatConversation) -> dict[str, str] | None:
    pending_actions = list(
        conversation.action_requests.filter(status=SystemIntelligenceActionRequest.STATUS_PENDING).order_by(
            "created_at"
        )[:20]
    )
    if not pending_actions:
        return None
    lines = [
        "Pending System Intelligence approval requests. These are not applied until an admin approves them:",
    ]
    for action in pending_actions:
        target = ".".join(part for part in [action.target_app_label, action.target_model] if part)
        if action.target_pk:
            target = f"{target} #{action.target_pk}" if target else f"#{action.target_pk}"
        lines.append(
            f"- {action.id}: {action.title} status={action.status} type={action.action_type} "
            f"target={target or 'unknown'} summary={action.summary or '(none)'}"
        )
    return {"role": "assistant", "content": "\n".join(lines)}


def summary_context_message(summary_text: str) -> dict[str, str]:
    return {
        "role": "assistant",
        "content": "Rolling summary of earlier System Intelligence conversation context:\n" + summary_text,
    }


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
