"""Model facts that differ by provider: whether a model accepts a custom temperature, and its context window."""

import logging
import re

from .presets import PRESETS

logger = logging.getLogger(__name__)

# Claude families with adaptive thinking reject custom sampling, whatever API serves them.
_FIXED_SAMPLING_CLAUDE = re.compile(
    r"(?:^|[/.:])claude-(?:fable-5|mythos-(?:5|preview)|opus-(?:5|4-[78])|sonnet-5)(?:[-.:/@]|$)"
)
# OpenAI reasoning models accept only the default temperature; Kimi thinking models fix sampling too.
_FIXED_SAMPLING_OPENAI = re.compile(r"(?:^|/)(?:o[1-9](?:-|$)|gpt-5)|kimi-k2-thinking")
DEFAULT_CONTEXT_WINDOW = 64_000
_MIN_WINDOW, _MAX_WINDOW = 4_000, 10_000_000


def supports_temperature(model_id: str, provider=None) -> bool:
    if provider is None:
        from apps.system_intelligence.services.bedrock.clients.parameters import supports_temperature as bedrock

        return bedrock(model_id)
    normalized = (model_id or "").strip().lower()
    return not (_FIXED_SAMPLING_CLAUDE.search(normalized) or _FIXED_SAMPLING_OPENAI.search(normalized))


def provider_context_window(model_id: str, provider) -> int:
    """The provider's configured window, else LiteLLM's model list, else a conservative default."""
    if provider.context_window_tokens:
        return provider.context_window_tokens
    model = (model_id or "").strip()
    preset = PRESETS.get(provider.preset)
    candidates = [model]
    if preset and preset.litellm_family:
        candidates.append(f"{preset.litellm_family}/{model}")
    for candidate in candidates:
        tokens = _litellm_max_input_tokens(candidate)
        if tokens:
            return tokens
    return DEFAULT_CONTEXT_WINDOW


def _litellm_max_input_tokens(model: str) -> int:
    if not model:
        return 0
    try:
        import litellm

        info = litellm.get_model_info(model)
    except Exception:  # noqa: BLE001 - an unmapped model is the common case
        return 0
    tokens = info.get("max_input_tokens") or 0
    return tokens if isinstance(tokens, int) and _MIN_WINDOW <= tokens <= _MAX_WINDOW else 0
