"""An API-key provider reaching ``litellm.acompletion`` through REAL Agents SDK objects: model string, base URL, key
and timeout per call, no AWS keys, nothing in ``os.environ``. Skipped without the ``openai-agents`` SDK."""

import asyncio
import socket
from importlib.util import find_spec
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.services.agents.definition.agent_builder import build_model_settings
from apps.system_intelligence.services.agents.definition.litellm import build_litellm_model, litellm_call_args
from apps.system_intelligence.services.agents.invocation.errors import SystemIntelligenceAgentError
from apps.system_intelligence.services.agents.invocation.runner import run_tool_free_agent, run_tool_free_agent_async
from apps.system_intelligence.services.agents.providers import ProviderConfigurationError

from .helpers import (
    TEST_API_KEY,
    ProviderStoreMixin,
    StopCall,
    assert_env_untouched,
    capture_acompletion,
    make_provider,
)

_AGENTS_INSTALLED = find_spec("agents") is not None
_AWS_KEYS = ("aws_access_key_id", "aws_secret_access_key", "aws_region_name")


def _public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _private_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]


@skipUnless(_AGENTS_INSTALLED, "openai-agents SDK not installed")
class ProviderLitellmCallTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        # Unsaved and unconfigured: a provider call must never need AWS credentials.
        self.aws_config = AWSCredentialConfig(name="empty")

    def _call(self, provider, model_id, temperature=0.2):
        async def go():
            try:
                await run_tool_free_agent_async(
                    system_text="sys",
                    input_data="hi",
                    aws_config=self.aws_config,
                    model_id=model_id,
                    max_tokens=64,
                    temperature=temperature,
                    provider=provider,
                )
            except StopCall:
                pass

        with capture_acompletion() as calls:
            asyncio.run(go())
            assert_env_untouched(self)
        self.assertTrue(calls, "litellm.acompletion was never called")
        return calls[0]

    def test_openai_format_preset_sends_model_base_url_key_and_timeout(self):
        provider = make_provider(request_timeout_seconds=45)
        captured = self._call(provider, " deepseek-chat ")
        self.assertEqual(captured["model"], "openai/deepseek-chat")
        self.assertEqual(captured["base_url"], "https://api.deepseek.com")
        self.assertEqual(captured["api_key"], TEST_API_KEY)
        self.assertEqual(captured["timeout"], 45)
        self.assertEqual(captured["temperature"], 0.2)
        for key in _AWS_KEYS:
            self.assertNotIn(key, captured)

    def test_anthropic_format_preset_uses_anthropic_prefix(self):
        provider = make_provider(name="Anthropic", preset="anthropic")
        captured = self._call(provider, "claude-sonnet-4-5")
        self.assertEqual(captured["model"], "anthropic/claude-sonnet-4-5")
        self.assertEqual(captured["base_url"], "https://api.anthropic.com")
        self.assertEqual(captured["api_key"], TEST_API_KEY)
        self.assertIsNone(captured.get("stream_options"))

    def test_fixed_sampling_models_omit_temperature(self):
        openai = make_provider(name="OpenAI", preset="openai")
        self.assertIsNone(self._call(openai, "gpt-5")["temperature"])
        anthropic = make_provider(name="Anthropic", preset="anthropic")
        self.assertIsNone(self._call(anthropic, "claude-opus-4-7")["temperature"])
        kimi = make_provider(name="Kimi", preset="moonshot")
        self.assertIsNone(self._call(kimi, "kimi-k2-thinking")["temperature"])

    def test_custom_endpoint_checks_dns_before_calling(self):
        provider = make_provider(
            name="Gateway", preset="custom", api_format="anthropic", base_url="https://gateway.example.com/v1"
        )
        with patch("socket.getaddrinfo", side_effect=_public_dns) as dns:
            captured = self._call(provider, "my-model")
        dns.assert_called()
        self.assertEqual(captured["model"], "anthropic/my-model")
        self.assertEqual(captured["base_url"], "https://gateway.example.com/v1")
        # A Custom endpoint is called through the redirect-refusing client (see providers.http_clients).
        from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler

        self.assertIsInstance(captured["client"], AsyncHTTPHandler)

    def test_custom_openai_endpoint_is_called_through_the_no_redirect_client(self):
        provider = make_provider(name="Gateway", preset="custom", base_url="https://gateway.example.com/v1")
        with patch("socket.getaddrinfo", side_effect=_public_dns):
            captured = self._call(provider, "gpt-4o")
        self.assertEqual(captured["model"], "openai/gpt-4o")
        self.assertFalse(captured["client"]._client.follow_redirects)

    def test_custom_endpoint_resolving_to_private_address_never_calls_litellm(self):
        provider = make_provider(name="Gateway", preset="custom", base_url="https://gateway.example.com/v1")
        with patch("socket.getaddrinfo", side_effect=_private_dns), capture_acompletion() as calls:
            with self.assertRaises(ProviderConfigurationError) as ctx:
                build_litellm_model(aws_config=self.aws_config, model_id="m", provider=provider)
        self.assertEqual(calls, [])
        self.assertIn('AI provider "Gateway"', str(ctx.exception))


class ProviderModelConstructionTests(ProviderStoreMixin, TestCase):
    def test_disabled_or_keyless_provider_is_refused_with_fixed_text(self):
        disabled = make_provider(enabled=False)
        with self.assertRaisesMessage(ProviderConfigurationError, 'The AI provider "DeepSeek" is disabled.'):
            build_litellm_model(aws_config=AWSCredentialConfig(name="x"), model_id="deepseek-chat", provider=disabled)
        keyless = make_provider(name="Kimi", preset="moonshot", enabled=False, with_key=False)
        keyless.is_enabled = True  # bypasses clean(): the runtime must still refuse it
        with self.assertRaisesMessage(ProviderConfigurationError, "has no API key installed"):
            build_litellm_model(aws_config=AWSCredentialConfig(name="x"), model_id="kimi-latest", provider=keyless)

    def test_custom_provider_without_base_url_is_refused(self):
        provider = make_provider(name="Gateway", preset="custom", base_url="")
        with patch("socket.getaddrinfo") as dns:
            with self.assertRaisesMessage(ProviderConfigurationError, 'The AI provider "Gateway" has no base URL.'):
                build_litellm_model(aws_config=AWSCredentialConfig(name="x"), model_id="m", provider=provider)
        dns.assert_not_called()

    def test_bedrock_route_still_requires_aws(self):
        with self.assertRaisesMessage(SystemIntelligenceAgentError, "AWS credentials are not configured"):
            build_litellm_model(aws_config=AWSCredentialConfig(name="x"), model_id="us.anthropic.claude-sonnet-4-5")

    @skipUnless(_AGENTS_INSTALLED, "openai-agents SDK not installed")
    def test_sync_tool_free_call_threads_the_provider(self):
        provider = make_provider()
        with capture_acompletion() as calls, self.assertRaises(StopCall):
            run_tool_free_agent(
                system_text="s", input_data="hi", aws_config=None, model_id="deepseek-chat", max_tokens=8,
                temperature=None, provider=provider,
            )  # fmt: skip
        self.assertEqual(calls[0]["model"], "openai/deepseek-chat")

    def test_blank_model_is_refused(self):
        provider = make_provider()
        with self.assertRaises(ProviderConfigurationError):
            build_litellm_model(aws_config=AWSCredentialConfig(name="x"), model_id="  ", provider=provider)

    def test_call_args_are_timeout_for_provider_and_aws_keys_for_bedrock(self):
        provider = make_provider(request_timeout_seconds=30)
        self.assertEqual(litellm_call_args(None, provider), {"timeout": 30})
        aws = AWSCredentialConfig(
            name="AWS", is_active=True, access_key_id="AKIA", secret_access_key="S", default_region="us-west-2"
        )
        self.assertEqual(
            litellm_call_args(aws),
            {"aws_access_key_id": "AKIA", "aws_secret_access_key": "S", "aws_region_name": "us-west-2"},
        )

    @skipUnless(_AGENTS_INSTALLED, "openai-agents SDK not installed")
    def test_model_settings_include_usage_only_for_openai_format(self):
        common = {"max_tokens": 10, "temperature": 0.5, "include_temperature": True, "extra_args": {"timeout": 9}}
        openai = make_provider()
        settings = build_model_settings(**common, model_id="deepseek-chat", provider=openai)
        self.assertTrue(settings.include_usage)
        self.assertEqual(settings.temperature, 0.5)
        self.assertEqual(settings.extra_args, {"timeout": 9})

        anthropic = make_provider(name="DeepSeek A", preset="deepseek_anthropic")
        self.assertIsNone(build_model_settings(**common, model_id="deepseek-chat", provider=anthropic).include_usage)
        bedrock = build_model_settings(**common, model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.assertIsNone(bedrock.include_usage)

    @skipUnless(_AGENTS_INSTALLED, "openai-agents SDK not installed")
    def test_model_settings_drop_temperature_for_fixed_sampling_provider_model(self):
        provider = make_provider(name="OpenAI", preset="openai")
        settings = build_model_settings(
            max_tokens=10, temperature=0.5, include_temperature=True, model_id="o3-mini", provider=provider
        )
        self.assertIsNone(settings.temperature)
