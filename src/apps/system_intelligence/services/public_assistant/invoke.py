"""Tool-free Bedrock Converse invocation for the public assistant.

This path is TOOL-FREE by construction: it builds the Converse request itself
and never attaches a ``toolConfig``, never imports the admin ADK tools, and
never reuses the admin system prompt. The only model id, prompt, and inference
parameters come from the public fields on ``SystemIntelligenceConfig``.
"""

import logging

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import BedrockError, normalize_bedrock_model_id
from apps.core.services.bedrock.clients import get_client

from .context import build_public_context

logger = logging.getLogger(__name__)

_VALID_ROLES = {"user", "assistant"}


def _trimmed_messages(history, message: str) -> list[dict]:
    """Build Bedrock content-block messages from history + the new user turn.

    Roles are coerced to user/assistant, blank turns dropped, and the new user
    message is always appended last so the request ends on a user turn.
    """
    messages: list[dict] = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role not in _VALID_ROLES or not content:
            continue
        messages.append({"role": role, "content": [{"text": content}]})
    messages.append({"role": "user", "content": [{"text": message}]})
    return messages


def _estimate_usage(system_text: str, message: str, reply_text: str) -> dict:
    """Conservative token estimate when Bedrock omits a usage block (~4 chars/token)."""
    output_tokens = len(reply_text) // 4
    input_tokens = (len(system_text) + len(message)) // 4
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


def _extract_text(response) -> str:
    content = response["output"]["message"]["content"]
    return "".join(block["text"] for block in content if "text" in block)


def answer_public_question(*, message, history, config, context=None) -> dict:
    """Answer a public question with a tool-free Bedrock Converse call.

    Returns ``{"text": str, "usage": {"inputTokens", "outputTokens", "totalTokens"}}``.
    Raises ``BedrockError`` if the model id is invalid or the call fails.
    """
    normalized_model_id = normalize_bedrock_model_id(config.public_model_id)
    if not normalized_model_id:
        raise BedrockError("No valid public assistant model is configured.")

    if context is None:
        context = build_public_context()
    system_text = config.public_assistant_system_prompt + "\n\nCONTEXT:\n" + (context or "")

    messages = _trimmed_messages(history, message)
    client = get_client(AWSCredentialConfig.load())

    base_kwargs = {
        "modelId": normalized_model_id,
        "messages": messages,
        "system": [{"text": system_text}],
    }
    inference = {
        "maxTokens": config.public_assistant_max_response_tokens,
        "temperature": config.public_assistant_temperature,
    }

    try:
        response = client.converse(**base_kwargs, inferenceConfig=inference)
    except Exception as exc:  # noqa: BLE001 - re-raised as BedrockError below
        # Some models reject `temperature`; retry once without it (best effort).
        if "temperature" in str(exc).lower():
            try:
                inference_no_temp = {"maxTokens": config.public_assistant_max_response_tokens}
                response = client.converse(**base_kwargs, inferenceConfig=inference_no_temp)
            except Exception as retry_exc:  # noqa: BLE001
                logger.exception("Public assistant Bedrock call failed on retry")
                raise BedrockError(f"Public assistant error: {retry_exc}") from retry_exc
        else:
            logger.exception("Public assistant Bedrock call failed")
            raise BedrockError(f"Public assistant error: {exc}") from exc

    text = _extract_text(response)
    usage = response.get("usage") or {}
    if not usage.get("totalTokens"):
        usage = _estimate_usage(system_text, message, text)
    return {"text": text, "usage": usage}
