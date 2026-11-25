"""Which provider and model one System Intelligence role calls, and whether it can be called right now.

A role is ``default`` (admin assistant, context summaries, scam review) or ``public`` (public chat, past-project AI
search). ``provider is None`` means Amazon Bedrock through the active AWS Credential Config.
"""

from dataclasses import dataclass
from typing import Any

from apps.system_intelligence.models.config_agent import DEFAULT_ROLE, PUBLIC_ROLE
from apps.system_intelligence.services.bedrock.models.catalog import normalize_bedrock_model_id

from ..invocation.errors import SystemIntelligenceAgentError

BEDROCK_LABEL = "Amazon Bedrock"
NO_MODEL = "No AI model is configured. Select a default model first."
NO_AWS = "AWS credentials are not configured. Add an active AWS Credential Config first."
DISABLED = 'The AI provider "{name}" is disabled.'
NO_KEY = 'The AI provider "{name}" has no API key installed.'

__all__ = ["DEFAULT_ROLE", "PUBLIC_ROLE", "ModelRoute", "ProviderConfigurationError", "resolve_route", "route_problem"]


class ProviderConfigurationError(SystemIntelligenceAgentError):
    """The configured provider cannot be called. The message is fixed text, safe to show to staff."""


@dataclass(frozen=True)
class ModelRoute:
    provider: Any  # LLMProviderConfig | None
    model_id: str

    @property
    def is_bedrock(self) -> bool:
        return self.provider is None

    @property
    def label(self) -> str:
        return BEDROCK_LABEL if self.provider is None else self.provider.name

    @property
    def log_model_id(self) -> str:
        """The model as recorded in audit logs: the Bedrock id, or ``<preset>/<model>`` for other providers."""
        if self.provider is None or not self.model_id:
            return self.model_id
        return f"{self.provider.preset}/{self.model_id}"[:256]

    @property
    def cache_key(self) -> str:
        """Identity for per-model caches (the temperature fallback): providers may share model names."""
        return self.model_id if self.provider is None else f"provider:{self.provider.pk}:{self.model_id}"


def resolve_route(config, role: str = DEFAULT_ROLE) -> ModelRoute:
    provider, model_id = config.route_for(role)
    if provider is None:
        return ModelRoute(None, normalize_bedrock_model_id(model_id))
    return ModelRoute(provider, (model_id or "").strip())


def route_problem(route: ModelRoute, *, aws_config=None) -> str:
    """Why *route* cannot be called (fixed text), or ``""``. Cheap: reads no secret and makes no network call."""
    if not route.model_id:
        return NO_MODEL
    if route.provider is None:
        if aws_config is None:
            from apps.core.models import AWSCredentialConfig

            aws_config = AWSCredentialConfig.load()
        return "" if aws_config.is_configured else NO_AWS
    if not route.provider.is_enabled:
        return DISABLED.format(name=route.provider.name)
    if not route.provider.key_configured:
        return NO_KEY.format(name=route.provider.name)
    return ""
