from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.services.credential_store import memory
from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.services.agents.providers.endpoints import PRIVATE_HOST, EndpointError
from apps.system_intelligence.services.agents.providers.keys import MISMATCH, NOT_INSTALLED, install_api_key
from apps.system_intelligence.services.agents.providers.litellm_args import (
    litellm_prefix,
    provider_call_args,
    provider_model_kwargs,
    wants_stream_usage,
)
from apps.system_intelligence.services.agents.providers.routing import NO_MODEL, ProviderConfigurationError

from . import make_keyed_provider, make_provider

ENSURE = "apps.system_intelligence.services.agents.providers.litellm_args.ensure_public_host"
API_KEY = "fake-fake-fake-1234"
Preset = LLMProviderConfig.Preset


@override_settings(CREDENTIAL_STORE_BACKEND="memory", CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=False)
class ProviderModelKwargsTests(TestCase):
    def setUp(self):
        cache.clear()
        memory.reset()
        self.addCleanup(memory.reset)

    def _ready(self, **fields):
        provider = make_provider(**fields)
        install_api_key(provider, API_KEY)
        provider.is_enabled = True
        provider.save(update_fields=["is_enabled"])
        return provider

    @patch(ENSURE)
    def test_openai_format_preset(self, ensure):
        provider = self._ready(preset=Preset.DEEPSEEK)
        kwargs = provider_model_kwargs(provider, "  deepseek-chat ")
        self.assertEqual(
            kwargs, {"model": "openai/deepseek-chat", "base_url": "https://api.deepseek.com", "api_key": API_KEY}
        )
        ensure.assert_not_called()

    @patch(ENSURE)
    def test_anthropic_format_preset(self, ensure):
        provider = self._ready(name="Kimi", preset=Preset.MOONSHOT_ANTHROPIC)
        kwargs = provider_model_kwargs(provider, "kimi-latest")
        self.assertEqual(kwargs["model"], "anthropic/kimi-latest")
        self.assertEqual(kwargs["base_url"], "https://api.moonshot.ai/anthropic")
        ensure.assert_not_called()

    @patch(ENSURE)
    def test_custom_endpoint_runs_dns_check(self, ensure):
        provider = self._ready(
            name="Gateway",
            preset=Preset.CUSTOM,
            api_format=LLMProviderConfig.ApiFormat.ANTHROPIC,
            base_url="https://gateway.example.com/v1",
        )
        kwargs = provider_model_kwargs(provider, "claude-x")
        ensure.assert_called_once_with("https://gateway.example.com/v1")
        self.assertEqual(
            kwargs, {"model": "anthropic/claude-x", "base_url": "https://gateway.example.com/v1", "api_key": API_KEY}
        )

    @patch(ENSURE, side_effect=EndpointError(PRIVATE_HOST))
    def test_custom_endpoint_dns_failure_is_wrapped(self, _ensure):
        provider = self._ready(name="Gateway", preset=Preset.CUSTOM, base_url="https://gateway.example.com")
        with self.assertRaises(ProviderConfigurationError) as ctx:
            provider_model_kwargs(provider, "gpt-4o")
        self.assertEqual(str(ctx.exception), f'AI provider "Gateway": {PRIVATE_HOST}')
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)

    def test_custom_endpoint_without_base_url(self):
        provider = make_keyed_provider(name="Bare", preset=Preset.CUSTOM, base_url="")
        with self.assertRaisesMessage(ProviderConfigurationError, 'The AI provider "Bare" has no base URL.'):
            provider_model_kwargs(provider, "gpt-4o")

    def test_route_problems_are_raised(self):
        with self.assertRaisesMessage(ProviderConfigurationError, NO_MODEL):
            provider_model_kwargs(make_keyed_provider(), "   ")
        with self.assertRaisesMessage(ProviderConfigurationError, NO_MODEL):
            provider_model_kwargs(make_keyed_provider(name="Other"), None)
        with self.assertRaisesMessage(ProviderConfigurationError, "is disabled"):
            provider_model_kwargs(make_provider(name="Off"), "deepseek-chat")

    def test_key_errors_are_wrapped(self):
        foreign = make_keyed_provider(name="Foreign")
        with self.assertRaisesMessage(ProviderConfigurationError, 'AI provider "Foreign": '):
            provider_model_kwargs(foreign, "deepseek-chat")

        donor = self._ready(name="Donor")
        copy = make_keyed_provider(
            name="Copy", key_secret_ref=donor.key_secret_ref, key_version_id=donor.key_version_id
        )
        with self.assertRaises(ProviderConfigurationError) as ctx:
            provider_model_kwargs(copy, "deepseek-chat")
        self.assertEqual(str(ctx.exception), f'AI provider "Copy": {MISMATCH}')
        self.assertNotIn(NOT_INSTALLED, str(ctx.exception))


class ProviderArgsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_litellm_prefix_follows_effective_format(self):
        self.assertEqual(litellm_prefix(LLMProviderConfig(preset=Preset.OPENAI)), "openai")
        self.assertEqual(litellm_prefix(LLMProviderConfig(preset=Preset.ANTHROPIC, api_format="openai")), "anthropic")
        self.assertEqual(litellm_prefix(LLMProviderConfig(preset=Preset.CUSTOM, api_format="anthropic")), "anthropic")
        self.assertEqual(litellm_prefix(LLMProviderConfig(preset=Preset.CUSTOM, api_format="openai")), "openai")

    def test_provider_call_args(self):
        self.assertEqual(provider_call_args(LLMProviderConfig(request_timeout_seconds=42)), {"timeout": 42})

    def test_wants_stream_usage(self):
        self.assertFalse(wants_stream_usage(None))
        self.assertTrue(wants_stream_usage(LLMProviderConfig(preset=Preset.MOONSHOT)))
        self.assertTrue(wants_stream_usage(LLMProviderConfig(preset=Preset.CUSTOM, api_format="openai")))
        self.assertFalse(wants_stream_usage(LLMProviderConfig(preset=Preset.DEEPSEEK_ANTHROPIC)))
        self.assertFalse(wants_stream_usage(LLMProviderConfig(preset=Preset.CUSTOM, api_format="anthropic")))
