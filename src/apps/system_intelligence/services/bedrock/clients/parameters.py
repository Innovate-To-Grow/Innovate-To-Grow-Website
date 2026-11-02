"""Sampling compatibility for Bedrock model and inference-profile IDs."""

import re

# These Claude families use adaptive thinking and reject custom sampling values.
# https://platform.claude.com/docs/en/about-claude/models/extended-thinking-models
_FIXED_SAMPLING = re.compile(
    r"anthropic\.claude-(?:fable-5|mythos-(?:5|preview)|opus-(?:5|4-[78])|sonnet-5)(?:[-.:/]|$)"
)


def supports_temperature(model_id: str) -> bool:
    return not bool(_FIXED_SAMPLING.search(model_id or ""))


def inference_config(*, model_id: str, max_tokens: int, temperature: float) -> dict:
    config = {"maxTokens": max_tokens}
    if supports_temperature(model_id):
        config["temperature"] = temperature
    return config
