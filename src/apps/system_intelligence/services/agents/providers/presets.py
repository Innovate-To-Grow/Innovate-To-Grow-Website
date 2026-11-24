"""Known AI providers: the API format and base URL each one fixes, and model names the admin form suggests.

Model names are suggestions only (the admin form accepts any name the provider serves). Base URLs are the provider's
documented roots: LiteLLM appends ``/chat/completions`` for the OpenAI format and ``/v1/messages`` for the Anthropic
format.
"""

from dataclasses import dataclass

OPENAI_FORMAT = "openai"
ANTHROPIC_FORMAT = "anthropic"


@dataclass(frozen=True)
class ProviderPreset:
    api_format: str
    base_url: str
    suggested_models: tuple[str, ...] = ()
    litellm_family: str = ""  # LiteLLM's own provider prefix, used only to look up model facts (context window)


_DEEPSEEK_MODELS = ("deepseek-chat", "deepseek-reasoner")
_KIMI_MODELS = ("kimi-k2-0905-preview", "kimi-k2-turbo-preview", "kimi-latest")

PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        OPENAI_FORMAT, "https://api.openai.com/v1", ("gpt-4.1", "gpt-4.1-mini", "gpt-4o"), "openai"
    ),
    "deepseek": ProviderPreset(OPENAI_FORMAT, "https://api.deepseek.com", _DEEPSEEK_MODELS, "deepseek"),
    "deepseek_anthropic": ProviderPreset(
        ANTHROPIC_FORMAT, "https://api.deepseek.com/anthropic", _DEEPSEEK_MODELS, "deepseek"
    ),
    "moonshot": ProviderPreset(OPENAI_FORMAT, "https://api.moonshot.ai/v1", _KIMI_MODELS, "moonshot"),
    "moonshot_cn": ProviderPreset(OPENAI_FORMAT, "https://api.moonshot.cn/v1", _KIMI_MODELS, "moonshot"),
    "moonshot_anthropic": ProviderPreset(
        ANTHROPIC_FORMAT, "https://api.moonshot.ai/anthropic", _KIMI_MODELS, "moonshot"
    ),
    "anthropic": ProviderPreset(
        ANTHROPIC_FORMAT,
        "https://api.anthropic.com",
        ("claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"),
        "anthropic",
    ),
}


def suggested_models(preset: str) -> tuple[str, ...]:
    entry = PRESETS.get(preset)
    return entry.suggested_models if entry else ()
