import asyncio
from unittest.mock import patch

from django.test import TransactionTestCase

from core.admin.system_intelligence.adk_web import SystemIntelligenceAgentLoader
from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import SystemIntelligenceConfig
from core.services.system_intelligence_adk.constants import APP_NAME, EXPORT_TOOL_NAMES, WRITE_TOOL_NAMES


class SystemIntelligenceAgentLoaderTests(TransactionTestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            system_prompt="Use tools.",
        )

    def test_loader_lists_single_system_intelligence_app(self):
        loader = SystemIntelligenceAgentLoader()

        self.assertEqual(loader.list_agents(), [APP_NAME])
        self.assertEqual(loader.list_agents_detailed()[0]["display_name"], "System Intelligence")

    def test_loader_builds_read_only_agent_for_adk_web(self):
        loader = SystemIntelligenceAgentLoader()
        with patch(
            "core.services.system_intelligence_adk.runner.build_lite_llm_model",
            return_value="bedrock/test-model",
        ):
            agent = loader.load_agent(APP_NAME)

        tool_names = {tool.__name__ for tool in agent.tools}
        self.assertFalse(tool_names & WRITE_TOOL_NAMES)
        self.assertFalse(tool_names & EXPORT_TOOL_NAMES)
        self.assertIsNone(agent.generate_content_config.temperature)

    def test_loader_builds_agent_from_async_adk_context(self):
        loader = SystemIntelligenceAgentLoader()

        async def load_agent():
            return loader.load_agent(APP_NAME)

        with patch(
            "core.services.system_intelligence_adk.runner.build_lite_llm_model",
            return_value="bedrock/test-model",
        ):
            agent = asyncio.run(load_agent())

        tool_names = {tool.__name__ for tool in agent.tools}
        self.assertFalse(tool_names & WRITE_TOOL_NAMES)
        self.assertFalse(tool_names & EXPORT_TOOL_NAMES)
        self.assertIsNone(agent.generate_content_config.temperature)

    def test_loader_rejects_unknown_agent(self):
        with self.assertRaises(ValueError):
            SystemIntelligenceAgentLoader().load_agent("other_agent")
