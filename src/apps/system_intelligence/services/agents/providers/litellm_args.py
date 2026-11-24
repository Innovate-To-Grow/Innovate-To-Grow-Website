"""LiteLLM arguments for an API-key provider: the model string, base URL and key for ``LitellmModel``, and the
per-call arguments merged into ``litellm.acompletion``.

The key goes only to the ``LitellmModel`` constructor (``ModelSettings.extra_args`` cannot carry ``api_key``), and is
always non-empty: an empty key would make LiteLLM fall back to process-wide env vars such as ``OPENAI_API_KEY``.
"""

from django.views.decorators.debug import sensitive_variables

from .endpoints import EndpointError, ensure_public_host
from .keys import ProviderKeyError, read_api_key
from .presets import ANTHROPIC_FORMAT
from .routing import ModelRoute, ProviderConfigurationError, route_problem

NO_BASE_URL = 'The AI provider "{name}" has no base URL.'


def litellm_prefix(provider) -> str:
    return "anthropic" if provider.effective_api_format == ANTHROPIC_FORMAT else "openai"


@sensitive_variables()
def provider_model_kwargs(provider, model_id: str) -> dict:
    """``LitellmModel(**kwargs)`` for *provider*. Raises ``ProviderConfigurationError`` (fixed text)."""
    problem = route_problem(ModelRoute(provider, (model_id or "").strip()))
    if problem:
        raise ProviderConfigurationError(problem)
    base_url = provider.effective_base_url
    if not base_url:
        raise ProviderConfigurationError(NO_BASE_URL.format(name=provider.name))
    try:
        if provider.is_custom:
            ensure_public_host(base_url)
        api_key = read_api_key(provider)
    except (EndpointError, ProviderKeyError) as exc:
        raise ProviderConfigurationError(f'AI provider "{provider.name}": {exc}') from None
    return {"model": f"{litellm_prefix(provider)}/{model_id.strip()}", "base_url": base_url, "api_key": api_key}


def provider_call_args(provider) -> dict:
    return {"timeout": provider.request_timeout_seconds}


def wants_stream_usage(provider) -> bool:
    """OpenAI-compatible hosts other than api.openai.com stream token usage only when asked (stream_options);
    LiteLLM's Anthropic route rejects that option."""
    return provider is not None and provider.effective_api_format != ANTHROPIC_FORMAT
