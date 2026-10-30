from unittest.mock import patch

from django.test import SimpleTestCase

from apps.system_intelligence.services.bedrock.clients.prepare import build_kwargs

from .test_invoke import FakeChatConfig


class SamplingParametersTests(SimpleTestCase):
    def test_fixed_sampling_models_omit_temperature_for_all_id_forms(self):
        models = [
            "us.anthropic.claude-fable-5",
            "global.anthropic.claude-fable-5-1",
            "anthropic.claude-mythos-preview",
            "anthropic.claude-mythos-5",
            "anthropic.claude-opus-4-7",
            "anthropic.claude-opus-4-8",
            "anthropic.claude-opus-5",
            "anthropic.claude-sonnet-5",
            "arn:aws:bedrock:us-west-2:123456789012:inference-profile/us.anthropic.claude-fable-5",
        ]
        with patch("apps.system_intelligence.services.bedrock.clients.prepare.get_tool_definitions", return_value=[]):
            for model in models:
                with self.subTest(model=model):
                    config = build_kwargs(FakeChatConfig(), model)["inferenceConfig"]
                    self.assertEqual(config, {"maxTokens": 1024})

    def test_other_models_keep_configured_temperature(self):
        with patch("apps.system_intelligence.services.bedrock.clients.prepare.get_tool_definitions", return_value=[]):
            for model in [
                "us.anthropic.claude-sonnet-4-20250514-v1:0",
                "anthropic.claude-opus-4-6",
                "amazon.nova-pro-v1:0",
            ]:
                with self.subTest(model=model):
                    config = build_kwargs(FakeChatConfig(), model)["inferenceConfig"]
                    self.assertEqual(config, {"maxTokens": 1024, "temperature": 0.5})
