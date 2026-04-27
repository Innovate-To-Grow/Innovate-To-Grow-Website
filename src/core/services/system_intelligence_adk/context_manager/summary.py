import asyncio
import logging
import uuid
from typing import Any

from django.utils import timezone
from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import ChatConversation, ChatMessage, SystemIntelligenceConfig

from ..constants import APP_NAME
from ..events import StreamState, normalize_adk_event
from ..litellm import build_lite_llm_model
from .messages import format_messages_for_summary
from .tokens import (
    SUMMARY_AGENT_NAME,
    SUMMARY_INPUT_TOKEN_LIMIT,
    SUMMARY_INSTRUCTION,
    SUMMARY_TARGET_TOKENS,
    trim_text_to_token_budget,
)

logger = logging.getLogger(__name__)


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


def fallback_context_summary(existing_summary: str, new_context: str) -> str:
    combined = "\n\n".join(part for part in [existing_summary.strip(), new_context.strip()] if part)
    return trim_text_to_token_budget(combined, SUMMARY_TARGET_TOKENS)
