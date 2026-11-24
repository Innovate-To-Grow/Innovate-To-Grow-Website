from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.system_intelligence.models import LLMProviderConfig, SystemIntelligenceConfig
from apps.system_intelligence.services.agents import providers
from apps.system_intelligence.services.agents.invocation.errors import SystemIntelligenceAgentError
from apps.system_intelligence.services.agents.providers.presets import PRESETS, suggested_models
from apps.system_intelligence.services.agents.providers.routing import (
    BEDROCK_LABEL,
    DEFAULT_ROLE,
    NO_AWS,
    NO_MODEL,
    PUBLIC_ROLE,
    ModelRoute,
    ProviderConfigurationError,
    resolve_route,
    route_problem,
)

from . import make_keyed_provider, make_provider

AWS_LOAD = "apps.core.models.AWSCredentialConfig.load"


class ModelRouteTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_bedrock_route_properties(self):
        route = ModelRoute(None, "us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.assertTrue(route.is_bedrock)
        self.assertEqual(route.label, BEDROCK_LABEL)
        self.assertEqual(route.log_model_id, "us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.assertEqual(route.cache_key, "us.anthropic.claude-sonnet-4-20250514-v1:0")

    def test_provider_route_properties(self):
        provider = make_provider(name="My DeepSeek")
        route = ModelRoute(provider, "deepseek-chat")
        self.assertFalse(route.is_bedrock)
        self.assertEqual(route.label, "My DeepSeek")
        self.assertEqual(route.log_model_id, "deepseek/deepseek-chat")
        self.assertEqual(route.cache_key, f"provider:{provider.pk}:deepseek-chat")
        self.assertEqual(ModelRoute(provider, "").log_model_id, "")
        self.assertEqual(len(ModelRoute(provider, "m" * 300).log_model_id), 256)

    def test_provider_configuration_error_is_an_agent_error(self):
        self.assertTrue(issubclass(ProviderConfigurationError, SystemIntelligenceAgentError))
        self.assertIs(providers.ProviderConfigurationError, ProviderConfigurationError)
        self.assertEqual((providers.DEFAULT_ROLE, providers.PUBLIC_ROLE), ("default", "public"))

    def test_suggested_models(self):
        self.assertEqual(suggested_models("deepseek"), ("deepseek-chat", "deepseek-reasoner"))
        self.assertEqual(suggested_models("custom"), ())
        self.assertEqual(suggested_models("nope"), ())
        for name, preset in PRESETS.items():
            with self.subTest(preset=name):
                self.assertTrue(preset.base_url.startswith("https://"))
                self.assertIn(name, LLMProviderConfig.Preset.values)


class ResolveRouteTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_bedrock_route_normalizes_model_id(self):
        config = SystemIntelligenceConfig(default_model_id="  bedrock/us.anthropic.claude-x-v1:0 ")
        route = resolve_route(config)
        self.assertEqual(route, ModelRoute(None, "us.anthropic.claude-x-v1:0"))

    def test_provider_route_strips_model_id(self):
        provider = make_provider()
        config = SystemIntelligenceConfig(default_provider=provider, default_model_id="  deepseek-chat \n")
        self.assertEqual(resolve_route(config, DEFAULT_ROLE), ModelRoute(provider, "deepseek-chat"))

    def test_provider_route_with_none_model_is_empty(self):
        provider = make_provider()
        config = SimpleNamespace(route_for=lambda role: (provider, None))
        self.assertEqual(resolve_route(config).model_id, "")

    def test_public_role_uses_public_provider_and_model(self):
        default = make_provider(name="Default")
        public = make_provider(name="Public", preset=LLMProviderConfig.Preset.MOONSHOT)
        config = SystemIntelligenceConfig(
            default_provider=default,
            default_model_id="deepseek-chat",
            public_assistant_provider=public,
            public_assistant_model_id=" kimi-latest ",
        )
        self.assertEqual(resolve_route(config, PUBLIC_ROLE), ModelRoute(public, "kimi-latest"))
        self.assertEqual(resolve_route(config, DEFAULT_ROLE), ModelRoute(default, "deepseek-chat"))


class RouteProblemTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_missing_model_comes_first(self):
        self.assertEqual(route_problem(ModelRoute(None, "")), NO_MODEL)
        self.assertEqual(route_problem(ModelRoute(make_provider(), "")), NO_MODEL)

    def test_bedrock_uses_given_aws_config(self):
        route = ModelRoute(None, "model")
        self.assertEqual(route_problem(route, aws_config=SimpleNamespace(is_configured=True)), "")
        self.assertEqual(route_problem(route, aws_config=SimpleNamespace(is_configured=False)), NO_AWS)

    def test_bedrock_loads_aws_config_when_not_given(self):
        route = ModelRoute(None, "model")
        with patch(AWS_LOAD, return_value=SimpleNamespace(is_configured=False)) as load:
            self.assertEqual(route_problem(route), NO_AWS)
        load.assert_called_once_with()
        with patch(AWS_LOAD, return_value=SimpleNamespace(is_configured=True)):
            self.assertEqual(route_problem(route), "")

    def test_bedrock_without_any_aws_config_row(self):
        self.assertEqual(route_problem(ModelRoute(None, "model")), NO_AWS)

    @patch(AWS_LOAD)
    def test_provider_checks_never_load_aws_config(self, load):
        disabled = make_keyed_provider(name="Off", is_enabled=False)
        self.assertEqual(route_problem(ModelRoute(disabled, "m")), 'The AI provider "Off" is disabled.')

        no_key = make_provider(name="Keyless", is_enabled=True)
        self.assertEqual(route_problem(ModelRoute(no_key, "m")), 'The AI provider "Keyless" has no API key installed.')

        ready = make_keyed_provider(name="Ready")
        self.assertEqual(route_problem(ModelRoute(ready, "m")), "")
        self.assertEqual(route_problem(ModelRoute(ready, "m"), aws_config=SimpleNamespace(is_configured=False)), "")
        load.assert_not_called()


class RouteForTests(TestCase):
    def setUp(self):
        cache.clear()
        self.default = make_provider(name="Default")
        self.public = make_provider(name="Public", preset=LLMProviderConfig.Preset.MOONSHOT)

    def test_default_role(self):
        config = SystemIntelligenceConfig(default_provider=self.default, default_model_id="deepseek-chat")
        self.assertEqual(config.route_for(), (self.default, "deepseek-chat"))
        self.assertEqual(config.route_for(DEFAULT_ROLE), (self.default, "deepseek-chat"))
        self.assertEqual(config.route_for("unknown"), (self.default, "deepseek-chat"))

    def test_public_role_with_public_model(self):
        config = SystemIntelligenceConfig(
            default_provider=self.default,
            default_model_id="deepseek-chat",
            public_assistant_provider=self.public,
            public_assistant_model_id="kimi-latest",
        )
        self.assertEqual(config.route_for(PUBLIC_ROLE), (self.public, "kimi-latest"))

    def test_public_model_on_bedrock_ignores_default_provider(self):
        config = SystemIntelligenceConfig(
            default_provider=self.default, default_model_id="deepseek-chat", public_assistant_model_id="us.claude-x"
        )
        self.assertEqual(config.route_for(PUBLIC_ROLE), (None, "us.claude-x"))

    def test_public_role_falls_back_to_default_when_model_blank(self):
        for blank in ("", "   ", None):
            with self.subTest(blank=blank):
                config = SystemIntelligenceConfig(
                    default_provider=self.default,
                    default_model_id="deepseek-chat",
                    public_assistant_provider=self.public,
                    public_assistant_model_id=blank,
                )
                self.assertEqual(config.route_for(PUBLIC_ROLE), (self.default, "deepseek-chat"))

    def test_bedrock_default(self):
        config = SystemIntelligenceConfig(default_model_id="us.anthropic.claude-x")
        self.assertEqual(config.route_for(PUBLIC_ROLE), (None, "us.anthropic.claude-x"))
