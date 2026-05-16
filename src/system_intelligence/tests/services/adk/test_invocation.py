import asyncio
from unittest.mock import patch

from django.test import TestCase
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types

from core.models import AWSCredentialConfig
from system_intelligence.models import SystemIntelligenceConfig
from system_intelligence.services.adk import (
    _TEMPERATURE_DEPRECATED_MODEL_IDS,
    AGENT_NAME,
    APP_NAME,
    _invoke_system_intelligence_stream_async,
)


class SystemIntelligenceADKInvocationTests(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            system_prompt="Use tools.",
        )

    def test_async_adapter_rebuilds_session_and_normalizes_runner_events(self):
        seen = {}

        class FakeRunner:
            async def run_async(self, *, user_id, session_id, new_message, run_config):
                seen.update(
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "new_message": new_message.parts[0].text,
                        "streaming_mode": run_config.streaming_mode.value,
                    }
                )
                yield Event(
                    author=AGENT_NAME,
                    partial=False,
                    content=types.Content(role="model", parts=[types.Part.from_text(text="Done")]),
                )

        async def collect():
            with patch(
                "system_intelligence.services.adk._build_runner",
                return_value=(FakeRunner(), InMemorySessionService()),
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
                        model_id=self.aws_config.default_model_id,
                        user_id="42",
                    )
                ]

        events = asyncio.run(collect())
        self.assertEqual(events, [{"type": "text", "chunk": "Done"}])
        self.assertEqual(seen["user_id"], "42")
        self.assertEqual(seen["new_message"], "Current")
        self.assertEqual(seen["streaming_mode"], "sse")
        self.assertTrue(seen["session_id"].startswith("si-"))

    def test_async_adapter_seeds_synthetic_summary_message_as_model_history(self):
        seen = {}
        session_service = InMemorySessionService()

        class FakeRunner:
            async def run_async(self, *, user_id, session_id, new_message, run_config):
                session = await session_service.get_session(
                    app_name=APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )
                seen["history"] = [
                    event.content.parts[0].text for event in session.events if event.content and event.content.parts
                ]
                seen["new_message"] = new_message.parts[0].text
                yield Event(
                    author=AGENT_NAME,
                    partial=False,
                    content=types.Content(role="model", parts=[types.Part.from_text(text="Done")]),
                )

        async def collect():
            with patch(
                "system_intelligence.services.adk._build_runner",
                return_value=(FakeRunner(), session_service),
            ):
                return [
                    event
                    async for event in _invoke_system_intelligence_stream_async(
                        [
                            {"role": "assistant", "content": "Rolling summary of earlier context."},
                            {"role": "user", "content": "Current"},
                        ],
                        chat_config=self.chat_config,
                        aws_config=self.aws_config,
                        model_id=self.aws_config.default_model_id,
                        user_id="42",
                    )
                ]

        self.assertEqual(asyncio.run(collect()), [{"type": "text", "chunk": "Done"}])
        self.assertEqual(seen["history"], ["Rolling summary of earlier context."])
        self.assertEqual(seen["new_message"], "Current")

    def test_async_adapter_retries_without_temperature_when_bedrock_deprecates_it(self):
        _TEMPERATURE_DEPRECATED_MODEL_IDS.clear()
        self.addCleanup(_TEMPERATURE_DEPRECATED_MODEL_IDS.clear)
        build_calls = []

        class TemperatureRejectedRunner:
            async def run_async(self, **kwargs):
                raise Exception("BedrockException: `temperature` is deprecated for this model.")
                yield Event(author=AGENT_NAME)

        class SuccessRunner:
            async def run_async(self, **kwargs):
                yield Event(
                    author=AGENT_NAME,
                    partial=False,
                    content=types.Content(role="model", parts=[types.Part.from_text(text="Retried")]),
                )

        def fake_build_runner(*, include_temperature, **kwargs):
            build_calls.append(include_temperature)
            return (TemperatureRejectedRunner() if include_temperature else SuccessRunner()), InMemorySessionService()

        async def collect():
            with patch("system_intelligence.services.adk._build_runner", side_effect=fake_build_runner):
                return [
                    event
                    async for event in _invoke_system_intelligence_stream_async(
                        [{"role": "user", "content": "Current"}],
                        chat_config=self.chat_config,
                        aws_config=self.aws_config,
                        model_id=self.aws_config.default_model_id,
                        user_id="42",
                    )
                ]

        self.assertEqual(asyncio.run(collect()), [{"type": "text", "chunk": "Retried"}])
        self.assertEqual(build_calls, [True, False])
