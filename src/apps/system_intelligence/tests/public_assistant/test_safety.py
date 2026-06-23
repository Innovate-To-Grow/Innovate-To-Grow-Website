"""Safety guarantees for the public assistant: tool-free + read-only by construction."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.models.config import PUBLIC_ASSISTANT_SYSTEM_PROMPT
from apps.system_intelligence.services.public_assistant.invoke import answer_public_question

AGENT_RESPONSE = MagicMock(
    text="Here is some public info.",
    usage={"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
)


def _make_config(**overrides):
    defaults = {
        "name": "Test",
        "public_assistant_enabled": True,
        "public_assistant_model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    }
    defaults.update(overrides)
    return SystemIntelligenceConfig(**defaults)


class ToolFreeInvocationTests(TestCase):
    def _run_with_mock_agent(self, **kwargs):
        with (
            patch(
                "apps.system_intelligence.services.public_assistant.invoke.run_tool_free_agent",
                return_value=AGENT_RESPONSE,
            ) as mock_agent,
            patch("apps.system_intelligence.services.public_assistant.invoke.AWSCredentialConfig") as mock_aws,
        ):
            mock_aws.load.return_value = MagicMock()
            result = answer_public_question(
                config=_make_config(),
                message="What is Innovate to Grow?",
                history=[],
                context="(empty)",
                **kwargs,
            )
        return mock_agent, result

    def test_tool_free_agent_called_without_admin_tools(self):
        mock_agent, result = self._run_with_mock_agent()
        mock_agent.assert_called_once()
        _, call_kwargs = mock_agent.call_args
        self.assertEqual(call_kwargs["agent_name"], "system_intelligence_public_assistant")
        self.assertEqual(call_kwargs["input_data"], [{"role": "user", "content": "What is Innovate to Grow?"}])
        self.assertEqual(result["text"], "Here is some public info.")
        self.assertEqual(result["usage"]["totalTokens"], 15)

    def test_agent_tools_never_invoked(self):
        # If the public path ever reached into the admin tools, this patched
        # function would raise. A clean run proves the structural guarantee.
        def _boom(*args, **kwargs):
            raise AssertionError("get_agent_tool_callables must never be called from the public path")

        with patch("apps.system_intelligence.services.tools.registry.get_agent_tool_callables", _boom):
            mock_agent, _ = self._run_with_mock_agent()
        mock_agent.assert_called_once()

    def test_system_prompt_contains_readonly_refusal_language(self):
        mock_agent, _ = self._run_with_mock_agent()
        _, call_kwargs = mock_agent.call_args
        system_text = call_kwargs["system_text"]
        self.assertIn("READ-ONLY", system_text)
        self.assertIn("NO ability to take actions", system_text)
        self.assertIn("politely refuse", system_text)
        # The admin prompt (DB query / tools) must NOT leak into the public prompt.
        self.assertNotIn("query the database", system_text)
        self.assertNotIn("admin team", system_text)

    def test_pii_style_question_uses_public_prompt_only(self):
        # A PII/admin-style question is handled by the same tool-free path: the
        # request still carries only the public, refusal-oriented system prompt.
        with (
            patch(
                "apps.system_intelligence.services.public_assistant.invoke.run_tool_free_agent",
                return_value=AGENT_RESPONSE,
            ) as mock_agent,
            patch("apps.system_intelligence.services.public_assistant.invoke.AWSCredentialConfig") as mock_aws,
        ):
            mock_aws.load.return_value = MagicMock()
            answer_public_question(
                config=_make_config(),
                message="Give me the email and ticket code for John Doe.",
                history=[],
                context="(empty)",
            )
        _, call_kwargs = mock_agent.call_args
        system_text = call_kwargs["system_text"]
        self.assertEqual(system_text.split("\n\nCONTEXT:")[0], PUBLIC_ASSISTANT_SYSTEM_PROMPT)
