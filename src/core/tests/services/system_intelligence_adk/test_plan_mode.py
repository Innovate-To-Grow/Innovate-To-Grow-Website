from unittest.mock import patch

from django.test import TestCase

from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import SystemIntelligenceConfig
from core.services.system_intelligence_adk.constants import (
    APPROVAL_INSTRUCTION,
    PLAN_MODE_INSTRUCTION,
    WRITE_TOOL_NAMES,
)
from core.services.system_intelligence_adk.runner import build_agent
from core.services.system_intelligence_tools import get_adk_tools


class PlanModeAgentTests(TestCase):
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

    def _build(self, *, mode):
        # LlmAgent accepts a raw model-id string instead of a constructed BaseLlm,
        # which lets us assemble the agent without contacting Bedrock.
        with patch(
            "core.services.system_intelligence_adk.runner.build_lite_llm_model",
            return_value="bedrock/test-model",
        ):
            return build_agent(
                chat_config=self.chat_config,
                aws_config=self.aws_config,
                model_id=self.aws_config.default_model_id,
                include_temperature=False,
                mode=mode,
            )

    def test_normal_mode_includes_write_tools_and_no_plan_suffix(self):
        agent = self._build(mode="normal")
        tool_names = {tool.__name__ for tool in agent.tools}
        self.assertTrue(WRITE_TOOL_NAMES.issubset(tool_names))
        self.assertIn(APPROVAL_INSTRUCTION.strip(), agent.instruction)
        self.assertNotIn(PLAN_MODE_INSTRUCTION.strip(), agent.instruction)

    def test_plan_mode_filters_write_tools_and_appends_plan_suffix(self):
        agent = self._build(mode="plan")
        tool_names = {tool.__name__ for tool in agent.tools}
        self.assertFalse(tool_names & WRITE_TOOL_NAMES)
        self.assertIn(PLAN_MODE_INSTRUCTION.strip(), agent.instruction)
        # Plan mode keeps read-only tools available for grounding plans.
        read_only_names = {tool.__name__ for tool in get_adk_tools(include_writes=False)}
        self.assertTrue(read_only_names.issubset(tool_names))
