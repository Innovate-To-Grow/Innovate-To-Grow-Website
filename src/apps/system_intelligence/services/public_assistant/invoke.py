"""Tool-free OpenAI Agents SDK invocation for the public assistant.

This path is TOOL-FREE by construction: it builds a tool-free agent, never
imports the admin tools, and never reuses the admin system prompt. The only
model id, prompt, and inference parameters come from the public fields on
``SystemIntelligenceConfig``.
"""

import logging

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import BedrockError, normalize_bedrock_model_id
from apps.system_intelligence.services.agents import run_tool_free_agent

from .context import build_public_context

logger = logging.getLogger(__name__)

_VALID_ROLES = {"user", "assistant"}


def _trimmed_messages(history, message: str) -> list[dict]:
    """Build agent input messages from history + the new user turn.

    Roles are coerced to user/assistant and blank turns dropped. The Bedrock
    Anthropic chat models behind the agent expect the transcript to begin with
    a user turn and to strictly alternate user/assistant; visitor-supplied
    history is untrusted, so we enforce both here before invoking the agent:

    - drop any leading assistant turns so the first turn is always ``user``;
    - collapse consecutive same-role turns, keeping the most recent one.

    The new user message is always appended last so the request ends on a user
    turn (merging into a trailing history ``user`` turn if present).
    """
    cleaned: list[dict] = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role not in _VALID_ROLES or not content:
            continue
        cleaned.append({"role": role, "text": content})

    messages: list[dict] = []
    for turn in cleaned:
        # Skip leading assistant turns: the transcript must start with a user.
        if not messages and turn["role"] != "user":
            continue
        # Collapse consecutive same-role turns (keep the latest content).
        if messages and messages[-1]["role"] == turn["role"]:
            messages[-1] = turn
            continue
        messages.append(turn)

    # Append the new user message, alternating correctly: if the transcript
    # already ends on a user turn, replace it so we don't emit user/user.
    if messages and messages[-1]["role"] == "user":
        messages[-1] = {"role": "user", "text": message}
    else:
        messages.append({"role": "user", "text": message})

    return [{"role": t["role"], "content": t["text"]} for t in messages]


def _estimate_usage(system_text: str, messages: list[dict], reply_text: str) -> dict:
    """Conservative token estimate when Bedrock omits a usage block (~4 chars/token).

    The input estimate covers the system prompt AND every message turn actually
    sent (history + the new user message), so the per-IP budget is not
    under-charged when prior turns are present.
    """
    output_tokens = len(reply_text) // 4
    message_chars = sum(len(turn["content"]) for turn in messages)
    input_tokens = (len(system_text) + message_chars) // 4
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


def _is_temperature_error(exc: Exception) -> bool:
    """True if the exception (or its cause chain) looks like a temperature rejection.

    Bedrock wording varies across models/SDK versions, so we walk ``__cause__``/
    ``__context__`` and match either the field name or a common phrasing rather
    than only the top-level ``str(exc)``.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if "temperature" in text or "sampling" in text:
            return True
        current = current.__cause__ or current.__context__
    return False


def answer_public_question(*, message, history, config, context=None) -> dict:
    """Answer a public question with a tool-free Agents SDK Bedrock call.

    Returns ``{"text": str, "usage": {"inputTokens", "outputTokens", "totalTokens"}}``.
    Raises ``BedrockError`` if the model id is invalid or the call fails.
    """
    normalized_model_id = normalize_bedrock_model_id(config.public_model_id)
    if not normalized_model_id:
        raise BedrockError("No valid public assistant model is configured.")

    if context is None:
        context = build_public_context()
    system_text = config.public_assistant_system_prompt
    if context:
        system_text += "\n\nCONTEXT:\n" + context

    messages = _trimmed_messages(history, message)
    aws_config = AWSCredentialConfig.load()

    try:
        result = run_tool_free_agent(
            system_text=system_text,
            input_data=messages,
            aws_config=aws_config,
            model_id=normalized_model_id,
            max_tokens=config.public_assistant_max_response_tokens,
            temperature=config.public_assistant_temperature,
            agent_name="system_intelligence_public_assistant",
        )
    except Exception as exc:  # noqa: BLE001 - re-raised as BedrockError below
        if _is_temperature_error(exc):
            try:
                result = run_tool_free_agent(
                    system_text=system_text,
                    input_data=messages,
                    aws_config=aws_config,
                    model_id=normalized_model_id,
                    max_tokens=config.public_assistant_max_response_tokens,
                    temperature=config.public_assistant_temperature,
                    include_temperature=False,
                    agent_name="system_intelligence_public_assistant",
                )
            except Exception as retry_exc:  # noqa: BLE001
                logger.exception("Public assistant agent call failed on retry")
                raise BedrockError(f"Public assistant error: {retry_exc}") from retry_exc
        else:
            logger.exception("Public assistant agent call failed")
            raise BedrockError(f"Public assistant error: {exc}") from exc

    text = result.text
    usage = result.usage or {}
    if not usage.get("totalTokens"):
        usage = _estimate_usage(system_text, messages, text)
    return {"text": text, "usage": usage}
