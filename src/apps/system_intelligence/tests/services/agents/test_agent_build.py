"""Regression tests that construct REAL OpenAI Agents SDK objects.

These guard the two defects the mocked unit tests cannot see, because every other
test patches above the ``from agents import ...`` seam:

- function_tool over the real tool callables (tools with open ``dict[str, Any]``
  params used to raise UserError under the SDK's default strict JSON schema), and
- per-call AWS credentials reaching ``litellm.acompletion`` via
  ``ModelSettings.extra_args`` instead of mutating process-global ``os.environ``.

Skipped when ``openai-agents`` is not installed so an SDK-less local checkout still
runs the rest of the suite; CI installs the SDK (requirements pin), so it runs there.
"""

import asyncio
import os
from importlib.util import find_spec
from unittest import skipUnless

from django.test import TestCase

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.agents.constants import EXPORT_TOOL_NAMES, WRITE_TOOL_NAMES
from apps.system_intelligence.services.agents.runner import build_agent, build_agent_tools, run_tool_free_agent_async
from apps.system_intelligence.services.tools import get_agent_tool_callables

_AGENTS_INSTALLED = find_spec("agents") is not None


@skipUnless(_AGENTS_INSTALLED, "openai-agents SDK not installed")
class RealAgentConstructionTests(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKIA-TEST",
            secret_access_key="SECRET-TEST",
            default_region="eu-central-1",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )

    def test_function_tool_wraps_every_tool_including_open_dict_params(self):
        wrapped = build_agent_tools()
        names = {tool.name for tool in wrapped}
        self.assertEqual(len(wrapped), len(get_agent_tool_callables()))
        # The tools whose dict[str, Any] params triggered the strict-schema UserError.
        for required in ("run_custom_query", "search_records", "propose_db_create", "export_records_to_excel"):
            self.assertIn(required, names)

    def test_plan_and_read_only_tool_lists_also_build(self):
        plan_names = {tool.name for tool in build_agent_tools(include_writes=False)}
        self.assertFalse(plan_names & WRITE_TOOL_NAMES)
        no_export_names = {tool.name for tool in build_agent_tools(include_exports=False)}
        self.assertFalse(no_export_names & EXPORT_TOOL_NAMES)

    def test_build_agent_attaches_per_call_aws_credentials_and_strips_plan_writes(self):
        agent = build_agent(
            chat_config=self.chat_config,
            aws_config=self.aws_config,
            model_id=self.chat_config.default_model_id,
        )
        self.assertEqual(
            agent.model_settings.extra_args,
            {
                "aws_access_key_id": "AKIA-TEST",
                "aws_secret_access_key": "SECRET-TEST",
                "aws_region_name": "eu-central-1",
            },
        )
        self.assertTrue({tool.name for tool in agent.tools} & WRITE_TOOL_NAMES)

        plan_agent = build_agent(
            chat_config=self.chat_config,
            aws_config=self.aws_config,
            model_id=self.chat_config.default_model_id,
            mode="plan",
        )
        self.assertFalse({tool.name for tool in plan_agent.tools} & WRITE_TOOL_NAMES)

    def test_credentials_reach_litellm_without_mutating_os_environ(self):
        import litellm

        captured: dict = {}

        class _Stop(Exception):
            pass

        async def fake_acompletion(*args, **kwargs):
            captured.update(kwargs)
            raise _Stop("captured")

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        removed = {
            key: os.environ.pop(key, None)
            for key in (
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_REGION_NAME",
                "AWS_REGION",
                "AWS_DEFAULT_REGION",
            )
        }
        try:

            async def go():
                try:
                    await run_tool_free_agent_async(
                        system_text="sys",
                        input_data="hi",
                        aws_config=self.aws_config,
                        model_id=self.chat_config.default_model_id,
                        max_tokens=64,
                        temperature=0.2,
                    )
                except _Stop:
                    pass

            asyncio.run(go())
        finally:
            litellm.acompletion = original
            for key, value in removed.items():
                if value is not None:
                    os.environ[key] = value

        self.assertEqual(captured.get("model"), "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.assertEqual(captured.get("aws_access_key_id"), "AKIA-TEST")
        self.assertEqual(captured.get("aws_secret_access_key"), "SECRET-TEST")
        self.assertEqual(captured.get("aws_region_name"), "eu-central-1")
        self.assertNotIn("AWS_ACCESS_KEY_ID", os.environ)
