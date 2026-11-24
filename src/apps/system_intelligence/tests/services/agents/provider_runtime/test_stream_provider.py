"""The admin agent stream with ``chat_config.default_provider`` set: no AWS needed, the provider reaches the runner,
the temperature fallback is keyed by the provider route, and errors are fixed text."""

import asyncio
from importlib.util import find_spec
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.agents import (
    _TEMPERATURE_DEPRECATED_MODEL_IDS,
    _invoke_system_intelligence_stream_async,
    invoke_system_intelligence_stream,
)
from apps.system_intelligence.services.agents.invocation.errors import SystemIntelligenceAgentError

from .helpers import TEST_API_KEY, ProviderStoreMixin, StopCall, capture_acompletion, make_provider

RUN_PATH = "apps.system_intelligence.services.agents.invocation.stream.run_agent_invocation"
BEDROCK_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"


class ProviderStreamTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        _TEMPERATURE_DEPRECATED_MODEL_IDS.clear()
        self.addCleanup(_TEMPERATURE_DEPRECATED_MODEL_IDS.clear)
        self.provider = make_provider()
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="SI", is_active=True, default_provider=self.provider, default_model_id="deepseek-chat"
        )

    def _collect(self, chat_config=None, aws_config=None):
        async def go():
            return [
                event
                async for event in _invoke_system_intelligence_stream_async(
                    [{"role": "user", "content": "Current"}],
                    chat_config=chat_config or self.chat_config,
                    aws_config=aws_config,
                    user_id="42",
                )
            ]

        return asyncio.run(go())

    def test_provider_config_streams_without_any_aws_config(self):
        self.assertFalse(AWSCredentialConfig.load().is_configured)
        seen = []

        async def fake_run(*args, **kwargs):
            seen.append(kwargs)
            yield {"type": "text", "chunk": "Hi"}

        with patch(RUN_PATH, side_effect=fake_run):
            events = self._collect()
        self.assertEqual(events, [{"type": "text", "chunk": "Hi"}])
        self.assertEqual(seen[0]["provider"], self.provider)
        self.assertIsNone(seen[0]["aws_config"])
        self.assertEqual(seen[0]["model_id"], "deepseek-chat")
        self.assertTrue(seen[0]["include_temperature"])

    def test_bedrock_config_still_requires_aws(self):
        bedrock = SystemIntelligenceConfig.objects.create(name="B", is_active=False, default_model_id=BEDROCK_MODEL)
        bedrock.is_active = True  # an in-memory active copy; save() would deactivate the provider config
        with patch(RUN_PATH) as run, self.assertRaisesMessage(SystemIntelligenceAgentError, "AWS credentials"):
            self._collect(chat_config=bedrock, aws_config=AWSCredentialConfig(name="empty"))
        run.assert_not_called()

    def test_temperature_retry_is_keyed_by_provider_route(self):
        calls = []

        async def fake_run(*args, include_temperature, **kwargs):
            calls.append(include_temperature)
            if include_temperature:
                raise Exception("Invalid temperature: only 1 is allowed for this model")
            yield {"type": "text", "chunk": "Retried"}

        with patch(RUN_PATH, side_effect=fake_run):
            self.assertEqual(self._collect(), [{"type": "text", "chunk": "Retried"}])
            self.assertEqual(calls, [True, False])
            key = f"provider:{self.provider.pk}:deepseek-chat"
            self.assertIn(key, _TEMPERATURE_DEPRECATED_MODEL_IDS)
            self.assertNotIn("deepseek-chat", _TEMPERATURE_DEPRECATED_MODEL_IDS)
            # The next turn skips temperature straight away.
            calls.clear()
            self._collect()
            self.assertEqual(calls, [False])

        # A Bedrock model with the same name keeps its temperature.
        aws = AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKIA", secret_access_key="S", default_region="us-west-2"
        )
        self.chat_config.default_provider = None
        calls.clear()
        with patch(RUN_PATH, side_effect=fake_run):
            self._collect(aws_config=aws)
        self.assertEqual(calls, [True, False])
        self.assertIn("deepseek-chat", _TEMPERATURE_DEPRECATED_MODEL_IDS)

    def test_non_temperature_error_is_not_retried(self):
        calls = []

        async def fake_run(*args, include_temperature, **kwargs):
            calls.append(include_temperature)
            raise RuntimeError("boom")
            yield {}

        with patch(RUN_PATH, side_effect=fake_run), self.assertRaises(RuntimeError):
            self._collect()
        self.assertEqual(calls, [True])
        self.assertNotIn(f"provider:{self.provider.pk}:deepseek-chat", _TEMPERATURE_DEPRECATED_MODEL_IDS)

    @skipUnless(find_spec("agents") is not None, "openai-agents SDK not installed")
    def test_real_streamed_call_asks_for_usage_and_carries_provider_kwargs(self):
        with capture_acompletion() as calls, self.assertRaises(StopCall):
            self._collect()
        captured = calls[0]
        self.assertTrue(captured["stream"])
        self.assertEqual(captured["stream_options"], {"include_usage": True})
        self.assertEqual(captured["model"], "openai/deepseek-chat")
        self.assertEqual(captured["base_url"], "https://api.deepseek.com")
        self.assertEqual(captured["api_key"], TEST_API_KEY)
        self.assertEqual(captured["timeout"], 120)
        self.assertNotIn("aws_access_key_id", captured)


class ProviderSyncStreamTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.provider = make_provider()
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="SI", is_active=True, default_provider=self.provider, default_model_id="deepseek-chat"
        )

    def _events(self, fake_stream):
        with patch(
            "apps.system_intelligence.services.agents._invoke_system_intelligence_stream_async", new=fake_stream
        ):
            return list(
                invoke_system_intelligence_stream([{"role": "user", "content": "Hi"}], chat_config=self.chat_config)
            )

    def test_sync_stream_needs_no_aws_and_passes_none(self):
        seen = {}

        async def ok_stream(*args, **kwargs):
            seen.update(kwargs)
            yield {"type": "text", "chunk": "ok"}

        self.assertEqual(self._events(ok_stream), [{"type": "text", "chunk": "ok"}])
        self.assertIsNone(seen["aws_config"])

    def test_sync_stream_reports_provider_error_as_fixed_text(self):
        from litellm.exceptions import AuthenticationError

        async def failing_stream(*args, **kwargs):
            raise AuthenticationError(message="Incorrect API key sk-leaked", llm_provider="openai", model="x")
            yield {}

        with self.assertLogs("apps.system_intelligence.services.agents.stream", level="ERROR"):
            events = self._events(failing_stream)
        self.assertEqual(
            events,
            [
                {
                    "type": "error",
                    "error": 'The AI provider "DeepSeek" rejected the API key. '
                    "Install a valid key on the AI provider page.",
                }
            ],
        )
        self.assertNotIn("sk-leaked", events[0]["error"])
