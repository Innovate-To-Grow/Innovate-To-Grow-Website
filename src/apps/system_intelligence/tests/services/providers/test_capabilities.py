from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.services.agents.providers.capabilities import (
    DEFAULT_CONTEXT_WINDOW,
    provider_context_window,
    supports_temperature,
)

GET_MODEL_INFO = "litellm.get_model_info"
Preset = LLMProviderConfig.Preset


class SupportsTemperatureTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.provider = LLMProviderConfig(preset=Preset.ANTHROPIC)

    def test_bedrock_delegates_to_bedrock_rules(self):
        self.assertFalse(supports_temperature("us.anthropic.claude-opus-4-7-v1:0"))
        self.assertTrue(supports_temperature("us.anthropic.claude-sonnet-4-20250514-v1:0"))
        # Bedrock rules need the "anthropic." vendor prefix; a bare name is not a Bedrock id.
        self.assertTrue(supports_temperature("claude-opus-4-7"))
        self.assertTrue(supports_temperature(None))

    def test_fixed_sampling_claude_families(self):
        for model in (
            "claude-opus-4-7",
            "claude-opus-4-8-20260101",
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-fable-5",
            "claude-mythos-5",
            "claude-mythos-preview",
            "anthropic/claude-opus-4-7",
            "anthropic.claude-sonnet-5",
            "us.anthropic.claude-opus-4-7-v1:0",
            "vertex:claude-opus-5",
            "claude-fable-5@20260101",
            "claude-sonnet-5.1",
            "  CLAUDE-OPUS-5  ",
        ):
            with self.subTest(model=model):
                self.assertFalse(supports_temperature(model, self.provider))

    def test_fixed_sampling_openai_and_kimi_models(self):
        for model in (
            "o1",
            "o1-mini",
            "o3-mini",
            "o4-mini",
            "openai/o3",
            "gpt-5",
            "gpt-5-mini",
            "openai/gpt-5-nano",
            "kimi-k2-thinking",
            "kimi-k2-thinking-turbo",
            "moonshot/kimi-k2-thinking",
        ):
            with self.subTest(model=model):
                self.assertFalse(supports_temperature(model, self.provider))

    def test_models_that_accept_temperature(self):
        for model in (
            "",
            None,
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-opus-4-6",
            "claude-opus-50",
            "claude-haiku-4-5",
            "gpt-4o",
            "gpt-4.1-mini",
            "o10",
            "foo-o1",
            "deepseek-chat",
            "kimi-k2-0905-preview",
        ):
            with self.subTest(model=model):
                self.assertTrue(supports_temperature(model, self.provider))


class ProviderContextWindowTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch(GET_MODEL_INFO)
    def test_configured_window_wins(self, get_model_info):
        provider = LLMProviderConfig(preset=Preset.DEEPSEEK, context_window_tokens=32_000)
        self.assertEqual(provider_context_window("deepseek-chat", provider), 32_000)
        get_model_info.assert_not_called()

    @patch(GET_MODEL_INFO, return_value={"max_input_tokens": 200_000})
    def test_bare_model_name_lookup(self, get_model_info):
        provider = LLMProviderConfig(preset=Preset.ANTHROPIC)
        self.assertEqual(provider_context_window(" claude-sonnet-4-5 ", provider), 200_000)
        get_model_info.assert_called_once_with("claude-sonnet-4-5")

    def test_family_prefix_lookup_after_bare_name_misses(self):
        provider = LLMProviderConfig(preset=Preset.MOONSHOT_CN)

        def info(model):
            if model == "moonshot/kimi-latest":
                return {"max_input_tokens": 131_072}
            raise Exception("This model isn't mapped yet.")

        with patch(GET_MODEL_INFO, side_effect=info) as get_model_info:
            self.assertEqual(provider_context_window("kimi-latest", provider), 131_072)
        self.assertEqual([c.args[0] for c in get_model_info.call_args_list], ["kimi-latest", "moonshot/kimi-latest"])

    def test_out_of_range_or_odd_values_fall_back(self):
        provider = LLMProviderConfig(preset=Preset.DEEPSEEK)
        for value in (None, 0, 3_999, 10_000_001, "128000", 128_000.0):
            with self.subTest(value=value), patch(GET_MODEL_INFO, return_value={"max_input_tokens": value}):
                self.assertEqual(provider_context_window("deepseek-chat", provider), DEFAULT_CONTEXT_WINDOW)

    @patch(GET_MODEL_INFO, return_value={"max_input_tokens": 4_000})
    def test_range_bounds_are_inclusive(self, _get_model_info):
        self.assertEqual(provider_context_window("m", LLMProviderConfig(preset=Preset.DEEPSEEK)), 4_000)

    @patch(GET_MODEL_INFO, side_effect=Exception("unmapped"))
    def test_custom_endpoint_has_no_family_candidate(self, get_model_info):
        provider = LLMProviderConfig(preset=Preset.CUSTOM, base_url="https://gateway.example.com")
        self.assertEqual(provider_context_window("my-model", provider), DEFAULT_CONTEXT_WINDOW)
        get_model_info.assert_called_once_with("my-model")

    @patch(GET_MODEL_INFO)
    def test_empty_model_never_looks_up(self, get_model_info):
        provider = LLMProviderConfig(preset=Preset.CUSTOM)
        self.assertEqual(provider_context_window(None, provider), DEFAULT_CONTEXT_WINDOW)
        self.assertEqual(provider_context_window("  ", provider), DEFAULT_CONTEXT_WINDOW)
        get_model_info.assert_not_called()
