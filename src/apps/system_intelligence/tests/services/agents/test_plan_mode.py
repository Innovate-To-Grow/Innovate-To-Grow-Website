from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.agents.constants import WRITE_TOOL_NAMES
from apps.system_intelligence.services.tools import get_agent_tool_callables


class SystemIntelligenceAgentPlanModeTests(TestCase):
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

    def test_plan_mode_invocation_disables_temperature_only_when_needed(self):
        seen = []

        async def fake_run_agent_invocation(*args, mode, include_temperature, **kwargs):
            seen.append((mode, include_temperature))
            yield {"type": "text", "chunk": "Plan"}

        async def collect():
            from apps.system_intelligence.services.agents import _invoke_system_intelligence_stream_async

            with patch(
                "apps.system_intelligence.services.agents.stream.run_agent_invocation",
                side_effect=fake_run_agent_invocation,
            ):
                return [
                    event
                    async for event in _invoke_system_intelligence_stream_async(
                        [{"role": "user", "content": "Plan this"}],
                        chat_config=self.chat_config,
                        aws_config=self.aws_config,
                        model_id=self.chat_config.default_model_id,
                        mode="plan",
                    )
                ]

        import asyncio

        self.assertEqual(asyncio.run(collect()), [{"type": "text", "chunk": "Plan"}])
        self.assertEqual(seen, [("plan", True)])


class SystemIntelligenceAgentToolFilteringTests(SimpleTestCase):
    def test_plan_mode_registry_strips_write_tools(self):
        read_only_names = {tool.__name__ for tool in get_agent_tool_callables(include_writes=False)}

        self.assertFalse(read_only_names & WRITE_TOOL_NAMES)
