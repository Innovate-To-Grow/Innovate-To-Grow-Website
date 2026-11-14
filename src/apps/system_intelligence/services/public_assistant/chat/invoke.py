"""Tool-free OpenAI Agents SDK invocation for the public assistant.

This path is TOOL-FREE by construction: it builds a tool-free agent, never
imports the admin tools, and never reuses the admin system prompt. The only
model id, prompt, and inference parameters come from the public fields on
``SystemIntelligenceConfig``.
"""

import logging

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.services.agents import run_tool_free_agent
from apps.system_intelligence.services.bedrock import BedrockError, normalize_bedrock_model_id

from .context import build_public_context
from .estimates import _estimate_usage
from .prompt import _system_text, _trimmed_messages

logger = logging.getLogger(__name__)


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
    system_text = _system_text(config, context)

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
