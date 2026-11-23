"""AI providers other than Amazon Bedrock: presets (``presets``), base-URL rules (``endpoints``), API keys in the
credential store (``keys``), per-role routing (``routing``), LiteLLM arguments (``litellm_args``), model facts
(``capabilities``) and admin-facing error text (``error_messages``)."""

from .routing import DEFAULT_ROLE, PUBLIC_ROLE, ModelRoute, ProviderConfigurationError, resolve_route, route_problem

__all__ = ["DEFAULT_ROLE", "PUBLIC_ROLE", "ModelRoute", "ProviderConfigurationError", "resolve_route", "route_problem"]
