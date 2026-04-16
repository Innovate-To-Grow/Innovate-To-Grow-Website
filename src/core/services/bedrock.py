"""Amazon Bedrock integration for AI chat using the Converse API.

Supports multi-turn tool use: when the model requests a tool call the loop
executes it locally via ``db_tools`` and feeds the result back until the
model produces a final text response.

Provides both synchronous (``invoke_bedrock``) and streaming
(``invoke_bedrock_stream``) interfaces.
"""

import json as _json
import logging

import boto3
from botocore.exceptions import ClientError
from django.core.cache import cache

from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import SystemIntelligenceConfig
from core.services.db_tools import execute_tool, get_tool_definitions

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
_MODEL_CACHE_KEY = "bedrock_available_models"
_MODEL_CACHE_TTL = 600  # 10 minutes

_FALLBACK_MODELS = [
    (
        "Anthropic Claude",
        [
            ("us.anthropic.claude-sonnet-4-20250514-v1:0", "Claude Sonnet 4"),
        ],
    ),
]


class BedrockError(Exception):
    """Raised when a Bedrock API call fails."""


def _get_aws_config(aws_config=None):
    if aws_config is None:
        aws_config = AWSCredentialConfig.load()
    if not aws_config.is_configured:
        raise BedrockError("AWS credentials are not configured. Add an active AWS Credential Config first.")
    return aws_config


def _get_client(aws_config=None):
    """Build a ``bedrock-runtime`` boto3 client from the active AWS credentials."""
    aws_config = _get_aws_config(aws_config)
    return boto3.client(
        "bedrock-runtime",
        region_name=aws_config.default_region or "us-west-2",
        aws_access_key_id=aws_config.access_key_id,
        aws_secret_access_key=aws_config.secret_access_key,
    )


def _get_management_client(aws_config=None):
    """Build a ``bedrock`` management client (for listing models/profiles)."""
    aws_config = _get_aws_config(aws_config)
    return boto3.client(
        "bedrock",
        region_name=aws_config.default_region or "us-west-2",
        aws_access_key_id=aws_config.access_key_id,
        aws_secret_access_key=aws_config.secret_access_key,
    )


# ---------------------------------------------------------------------------
# Dynamic model discovery
# ---------------------------------------------------------------------------


def get_available_models(force_refresh=False):
    """Return available Bedrock models grouped by provider.

    Returns a list of ``(group_name, [(model_id, display_name), ...])`` tuples,
    combining inference profiles (cross-region IDs like ``us.anthropic.*``)
    with on-demand foundation models.

    Results are cached for 10 minutes. Falls back to a minimal hardcoded list
    if the AWS API call fails.
    """
    if not force_refresh:
        cached = cache.get(_MODEL_CACHE_KEY)
        if cached is not None:
            return cached

    try:
        result = _fetch_models_from_aws()
        cache.set(_MODEL_CACHE_KEY, result, _MODEL_CACHE_TTL)
        return result
    except Exception:
        logger.exception("Failed to fetch Bedrock models from AWS, using fallback")
        return _FALLBACK_MODELS


def _fetch_models_from_aws():
    """Call AWS APIs to build the grouped model list."""
    mgmt = _get_management_client()

    # Collect inference profiles first -- these are the preferred IDs
    profiles_by_provider = {}
    try:
        paginator = mgmt.get_paginator("list_inference_profiles")
        for page in paginator.paginate():
            for profile in page.get("inferenceProfileSummaries", []):
                if profile.get("type") != "SYSTEM_DEFINED":
                    continue
                pid = profile["inferenceProfileId"]
                name = profile.get("inferenceProfileName", pid)
                # Derive provider from the profile ARN or ID
                provider = _provider_from_id(pid)
                profiles_by_provider.setdefault(provider, []).append((pid, name))
    except Exception:
        logger.warning("list_inference_profiles failed, will use foundation models only")

    # Also fetch foundation models for any not covered by profiles
    fm_by_provider = {}
    try:
        resp = mgmt.list_foundation_models(
            byOutputModality="TEXT",
            byInferenceType="ON_DEMAND",
        )
        for model in resp.get("modelSummaries", []):
            mid = model["modelId"]
            name = model.get("modelName", mid)
            provider = model.get("providerName", "Other")
            fm_by_provider.setdefault(provider, []).append((mid, name))
    except Exception:
        logger.warning("list_foundation_models failed")

    # Merge: prefer inference profiles, supplement with foundation models
    all_providers = set(profiles_by_provider) | set(fm_by_provider)
    if not all_providers:
        return _FALLBACK_MODELS

    # Track which base model IDs are already covered by profiles
    profile_base_ids = set()
    for models in profiles_by_provider.values():
        for pid, _ in models:
            # e.g. "us.anthropic.claude-sonnet-4-20250514-v1:0" covers "anthropic.claude-sonnet-4-20250514-v1:0"
            parts = pid.split(".", 1)
            if len(parts) == 2 and len(parts[0]) <= 3:
                profile_base_ids.add(parts[1])

    grouped = []
    for provider in sorted(all_providers):
        models = list(profiles_by_provider.get(provider, []))
        # Add foundation models not already covered by a profile
        for mid, name in fm_by_provider.get(provider, []):
            if mid not in profile_base_ids and not any(m[0] == mid for m in models):
                models.append((mid, name))
        if models:
            models.sort(key=lambda m: m[1])
            grouped.append((provider, models))

    return grouped if grouped else _FALLBACK_MODELS


def _provider_from_id(model_id):
    """Extract a human-friendly provider name from a model/profile ID."""
    mapping = {
        "anthropic": "Anthropic",
        "amazon": "Amazon",
        "meta": "Meta",
        "mistral": "Mistral",
        "cohere": "Cohere",
        "ai21": "AI21 Labs",
        "stability": "Stability AI",
    }
    # Strip region prefix like "us." or "eu."
    clean = model_id
    parts = model_id.split(".", 1)
    if len(parts) == 2 and len(parts[0]) <= 3:
        clean = parts[1]
    vendor = clean.split(".")[0].lower()
    return mapping.get(vendor, vendor.title())


def _build_kwargs(chat_config, model_id):
    """Build common kwargs shared by converse and converse_stream."""
    kwargs = {
        "modelId": model_id,
        "inferenceConfig": {
            "maxTokens": chat_config.max_tokens,
            "temperature": chat_config.temperature,
        },
    }
    if chat_config.system_prompt:
        kwargs["system"] = [{"text": chat_config.system_prompt}]

    tool_defs = get_tool_definitions()
    if tool_defs:
        kwargs["toolConfig"] = {"tools": tool_defs}

    return kwargs


def _prepare(conversation_messages, chat_config, aws_config, model_id=None):
    """Validate configs and return (client, messages, kwargs)."""
    if chat_config is None:
        chat_config = SystemIntelligenceConfig.load()
    if not chat_config.is_configured:
        raise BedrockError("AI Chat is not configured. Add an active AI Chat Config first.")

    if not model_id:
        model_id = AWSCredentialConfig.load().default_model_id

    client = _get_client(aws_config)
    messages = [{"role": m["role"], "content": [{"text": m["content"]}]} for m in conversation_messages]
    kwargs = _build_kwargs(chat_config, model_id)
    return client, messages, kwargs


# ---------------------------------------------------------------------------
# Synchronous (non-streaming) interface — kept for backward compat
# ---------------------------------------------------------------------------


def invoke_bedrock(conversation_messages, *, chat_config=None, aws_config=None, model_id=None):
    """Call the Bedrock Converse API (non-streaming).

    Returns ``{"text": str, "tool_calls": list[dict]}``.
    """
    client, messages, kwargs = _prepare(conversation_messages, chat_config, aws_config, model_id)
    tool_calls_log = []

    for round_num in range(MAX_TOOL_ROUNDS):
        kwargs["messages"] = messages
        try:
            response = client.converse(**kwargs)
        except ClientError as exc:
            logger.exception("Bedrock Converse API error (round %d)", round_num)
            raise BedrockError(f"Bedrock API error: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error calling Bedrock (round %d)", round_num)
            raise BedrockError(f"Unexpected error: {exc}") from exc

        output_message = response["output"]["message"]
        messages.append(output_message)

        if response.get("stopReason") == "tool_use":
            tool_results = []
            for block in output_message["content"]:
                if "toolUse" in block:
                    tool_info = block["toolUse"]
                    result_text = execute_tool(tool_info)
                    tool_calls_log.append(
                        {
                            "name": tool_info.get("name", "unknown"),
                            "input": tool_info.get("input", {}),
                            "result_preview": result_text[:200],
                        }
                    )
                    tool_results.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_info["toolUseId"],
                                "content": [{"text": result_text}],
                            }
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        text_parts = [b["text"] for b in output_message["content"] if "text" in b]
        return {"text": "".join(text_parts), "tool_calls": tool_calls_log}

    return {
        "text": "I was unable to complete the request within the allowed number of steps.",
        "tool_calls": tool_calls_log,
    }


# ---------------------------------------------------------------------------
# Streaming interface — yields SSE-ready event dicts
# ---------------------------------------------------------------------------


def invoke_bedrock_stream(conversation_messages, *, chat_config=None, aws_config=None, model_id=None):
    """Call the Bedrock ConverseStream API with tool-use loop.

    Yields dicts of the form:
    - ``{"type": "text", "chunk": "..."}`` for each text delta
    - ``{"type": "tool_call", "name": "...", "input": {...}, "result_preview": "..."}``
    - ``{"type": "error", "error": "..."}`` on failure

    The caller is responsible for assembling the final text and emitting
    a ``done`` SSE event after the generator is exhausted.
    """
    try:
        client, messages, kwargs = _prepare(conversation_messages, chat_config, aws_config, model_id)
    except BedrockError as exc:
        yield {"type": "error", "error": str(exc)}
        return

    for round_num in range(MAX_TOOL_ROUNDS):
        kwargs["messages"] = messages

        try:
            response = client.converse_stream(**kwargs)
        except ClientError as exc:
            logger.exception("Bedrock ConverseStream error (round %d)", round_num)
            yield {"type": "error", "error": f"Bedrock API error: {exc}"}
            return
        except Exception as exc:
            logger.exception("Unexpected error calling Bedrock stream (round %d)", round_num)
            yield {"type": "error", "error": f"Unexpected error: {exc}"}
            return

        # State for accumulating the assistant message across stream events
        content_blocks = []
        current_block = {}
        stop_reason = "end_turn"
        tool_use_input_buf = ""

        for event in response.get("stream", []):
            if "contentBlockStart" in event:
                start = event["contentBlockStart"].get("start", {})
                if "toolUse" in start:
                    current_block = {
                        "type": "toolUse",
                        "toolUseId": start["toolUse"]["toolUseId"],
                        "name": start["toolUse"]["name"],
                    }
                    tool_use_input_buf = ""
                else:
                    current_block = {"type": "text", "text": ""}

            elif "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    current_block.setdefault("text", "")
                    current_block["text"] += delta["text"]
                    yield {"type": "text", "chunk": delta["text"]}
                elif "toolUse" in delta:
                    tool_use_input_buf += delta["toolUse"].get("input", "")

            elif "contentBlockStop" in event:
                if current_block.get("type") == "toolUse":
                    try:
                        parsed_input = _json.loads(tool_use_input_buf) if tool_use_input_buf else {}
                    except _json.JSONDecodeError:
                        parsed_input = {}
                    current_block["input"] = parsed_input
                    content_blocks.append(
                        {
                            "toolUse": {
                                "toolUseId": current_block["toolUseId"],
                                "name": current_block["name"],
                                "input": parsed_input,
                            }
                        }
                    )
                else:
                    content_blocks.append({"text": current_block.get("text", "")})
                current_block = {}
                tool_use_input_buf = ""

            elif "messageStop" in event:
                stop_reason = event["messageStop"].get("stopReason", "end_turn")

        # Rebuild the full assistant message for the conversation history
        assistant_message = {"role": "assistant", "content": content_blocks}
        messages.append(assistant_message)

        if stop_reason == "tool_use":
            tool_results = []
            for block in content_blocks:
                if "toolUse" in block:
                    tool_info = block["toolUse"]
                    logger.info("Stream tool call round %d: %s", round_num, tool_info.get("name"))
                    result_text = execute_tool(tool_info)
                    yield {
                        "type": "tool_call",
                        "name": tool_info.get("name", "unknown"),
                        "input": tool_info.get("input", {}),
                        "result_preview": result_text[:200],
                    }
                    tool_results.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_info["toolUseId"],
                                "content": [{"text": result_text}],
                            }
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        # end_turn — stream is done
        return

    yield {"type": "error", "error": "Too many tool-use rounds."}
