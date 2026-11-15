import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.agents import (
    _TEMPERATURE_DEPRECATED_MODEL_IDS,
    _invoke_system_intelligence_stream_async,
)


class _SystemIntelligenceAgentInvocationCase(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )


class SystemIntelligenceAgentInvocationTests(_SystemIntelligenceAgentInvocationCase):
    def test_async_adapter_streams_text_and_usage_from_agents_runner(self):
        class FakeStreamingResult:
            context_wrapper = SimpleNamespace(usage=SimpleNamespace(input_tokens=8, output_tokens=3, total_tokens=11))

            async def stream_events(self):
                yield SimpleNamespace(
                    type="raw_response_event",
                    data=SimpleNamespace(type="response.output_text.delta", delta="Done"),
                )

        class FakeRunner:
            @classmethod
            def run_streamed(cls, agent, *, input, max_turns, run_config):
                self.assertEqual(input[-1], {"role": "user", "content": "Current"})
                self.assertEqual(max_turns, 24)
                self.assertFalse(run_config.trace_include_sensitive_data)
                return FakeStreamingResult()

        async def collect():
            with (
                patch("apps.system_intelligence.services.agents.runner.runner_class", return_value=FakeRunner),
                patch(
                    "apps.system_intelligence.services.agents.runner.build_run_config",
                    return_value=SimpleNamespace(trace_include_sensitive_data=False),
                ),
                patch("apps.system_intelligence.services.agents._build_agent", return_value=object()),
            ):
                return [
                    event
                    async for event in _invoke_system_intelligence_stream_async(
                        [
                            {"role": "user", "content": "Earlier"},
                            {"role": "assistant", "content": "Previous answer"},
                            {"role": "user", "content": "Current"},
                        ],
                        chat_config=self.chat_config,
                        aws_config=self.aws_config,
                        model_id=self.chat_config.default_model_id,
                        user_id="42",
                    )
                ]

        self.assertEqual(
            asyncio.run(collect()),
            [
                {"type": "text", "chunk": "Done"},
                {"type": "usage", "inputTokens": 8, "outputTokens": 3, "totalTokens": 11},
            ],
        )

    def test_async_adapter_retries_without_temperature_when_bedrock_rejects_it(self):
        _TEMPERATURE_DEPRECATED_MODEL_IDS.clear()
        self.addCleanup(_TEMPERATURE_DEPRECATED_MODEL_IDS.clear)
        build_calls = []

        async def fake_run_agent_invocation(*args, include_temperature, **kwargs):
            build_calls.append(include_temperature)
            if include_temperature:
                raise Exception("BedrockException: `temperature` is deprecated for this model.")
            yield {"type": "text", "chunk": "Retried"}

        async def collect():
            with patch(
                "apps.system_intelligence.services.agents.stream.run_agent_invocation",
                side_effect=fake_run_agent_invocation,
            ):
                return [
                    event
                    async for event in _invoke_system_intelligence_stream_async(
                        [{"role": "user", "content": "Current"}],
                        chat_config=self.chat_config,
                        aws_config=self.aws_config,
                        model_id=self.chat_config.default_model_id,
                        user_id="42",
                    )
                ]

        self.assertEqual(asyncio.run(collect()), [{"type": "text", "chunk": "Retried"}])
        self.assertEqual(build_calls, [True, False])

    def test_async_adapter_retries_without_temperature_when_litellm_rejects_it(self):
        _TEMPERATURE_DEPRECATED_MODEL_IDS.clear()
        self.addCleanup(_TEMPERATURE_DEPRECATED_MODEL_IDS.clear)
        build_calls = []

        async def fake_run_agent_invocation(*args, include_temperature, **kwargs):
            build_calls.append(include_temperature)
            if include_temperature:
                raise Exception(
                    "litellm.UnsupportedParamsError: us.anthropic.claude-opus-4-7 "
                    "does not support temperature=0.7. Only temperature=1 is supported."
                )
            yield {"type": "text", "chunk": "Retried"}

        async def collect():
            with patch(
                "apps.system_intelligence.services.agents.stream.run_agent_invocation",
                side_effect=fake_run_agent_invocation,
            ):
                return [
                    event
                    async for event in _invoke_system_intelligence_stream_async(
                        [{"role": "user", "content": "Current"}],
                        chat_config=self.chat_config,
                        aws_config=self.aws_config,
                        model_id=self.chat_config.default_model_id,
                        user_id="42",
                    )
                ]

        self.assertEqual(asyncio.run(collect()), [{"type": "text", "chunk": "Retried"}])
        self.assertEqual(build_calls, [True, False])
