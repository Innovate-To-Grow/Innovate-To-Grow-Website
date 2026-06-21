"""Unit tests for the tool-free public assistant invocation service."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.services.bedrock import BedrockError
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import invoke


def _config(**overrides):
    defaults = {
        "name": "Test",
        "public_assistant_model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "public_assistant_max_response_tokens": 1024,
        "public_assistant_temperature": 0.3,
    }
    defaults.update(overrides)
    return SystemIntelligenceConfig(**defaults)


def _agent_result(text="hello", usage=None):
    return MagicMock(
        text=text, usage=usage if usage is not None else {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}
    )


class InvokeTests(TestCase):
    @contextmanager
    def _patch_agent(self, result):
        with (
            patch("apps.system_intelligence.services.public_assistant.invoke.run_tool_free_agent") as mock_agent,
            patch("apps.system_intelligence.services.public_assistant.invoke.AWSCredentialConfig") as mock_aws,
        ):
            mock_agent.return_value = result
            yield {"run_tool_free_agent": mock_agent, "AWSCredentialConfig": mock_aws}

    def test_no_model_raises(self):
        with self.assertRaises(BedrockError):
            invoke.answer_public_question(
                config=_config(public_assistant_model_id="", default_model_id=""),
                message="hi",
                history=[],
                context="",
            )

    def test_history_roles_coerced_and_message_appended(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "system", "content": "dropped"},
            {"role": "user", "content": "   "},
            "not-a-dict",
        ]
        with self._patch_agent(_agent_result("ans")) as patched:
            invoke.answer_public_question(config=_config(), message="newest", history=history, context="ctx")
        sent_messages = patched["run_tool_free_agent"].call_args.kwargs["input_data"]
        self.assertEqual(len(sent_messages), 3)
        self.assertEqual(sent_messages[-1], {"role": "user", "content": "newest"})
        self.assertEqual(sent_messages[0]["content"], "first")

    def test_usage_estimated_when_missing(self):
        with self._patch_agent(_agent_result("a" * 40, usage={})) as patched:
            result = invoke.answer_public_question(config=_config(), message="question", history=[], context="x")
        patched["run_tool_free_agent"].assert_called_once()
        self.assertGreater(result["usage"]["outputTokens"], 0)
        self.assertEqual(
            result["usage"]["totalTokens"],
            result["usage"]["inputTokens"] + result["usage"]["outputTokens"],
        )

    def test_estimate_includes_history_tokens(self):
        long_history = [{"role": "user", "content": "h" * 4000}, {"role": "assistant", "content": "r" * 4000}]
        with self._patch_agent(_agent_result("ans", usage={})):
            with_hist = invoke.answer_public_question(config=_config(), message="q", history=long_history, context="x")
            without_hist = invoke.answer_public_question(config=_config(), message="q", history=[], context="x")
        self.assertGreater(with_hist["usage"]["inputTokens"], without_hist["usage"]["inputTokens"])

    def test_leading_assistant_history_dropped(self):
        history = [{"role": "assistant", "content": "I am the assistant"}]
        with self._patch_agent(_agent_result("ans")) as patched:
            invoke.answer_public_question(config=_config(), message="hi", history=history, context="x")
        sent = patched["run_tool_free_agent"].call_args.kwargs["input_data"]
        self.assertEqual(sent[0]["role"], "user")
        self.assertTrue(all(m["role"] != "assistant" or i > 0 for i, m in enumerate(sent)))

    def test_consecutive_same_role_collapsed(self):
        history = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
        with self._patch_agent(_agent_result("ans")) as patched:
            invoke.answer_public_question(config=_config(), message="c", history=history, context="x")
        roles = [m["role"] for m in patched["run_tool_free_agent"].call_args.kwargs["input_data"]]
        self.assertTrue(all(roles[i] != roles[i + 1] for i in range(len(roles) - 1)))
        self.assertEqual(roles[-1], "user")

    def test_empty_context_omits_dangling_header(self):
        with self._patch_agent(_agent_result("ans")) as patched:
            invoke.answer_public_question(config=_config(), message="hi", history=[], context="")
        system_text = patched["run_tool_free_agent"].call_args.kwargs["system_text"]
        self.assertNotIn("CONTEXT:", system_text)

    def test_temperature_error_detected_in_cause_chain(self):
        wrapped = RuntimeError("request failed")
        wrapped.__cause__ = ValueError("ValidationException: temperature not supported")
        runner = MagicMock(side_effect=[wrapped, _agent_result("ok")])
        with patch.multiple(
            "apps.system_intelligence.services.public_assistant.invoke",
            run_tool_free_agent=runner,
            AWSCredentialConfig=MagicMock(),
        ):
            result = invoke.answer_public_question(config=_config(), message="hi", history=[], context="x")
        self.assertEqual(result["text"], "ok")
        self.assertEqual(runner.call_count, 2)
        self.assertFalse(runner.call_args.kwargs["include_temperature"])

    def test_context_built_when_not_provided(self):
        with (
            self._patch_agent(_agent_result("ans")) as patched,
            patch.object(invoke, "build_public_context", return_value="GENERATED CONTEXT") as mock_ctx,
        ):
            invoke.answer_public_question(config=_config(), message="hi", history=[])
        mock_ctx.assert_called_once()
        system_text = patched["run_tool_free_agent"].call_args.kwargs["system_text"]
        self.assertIn("GENERATED CONTEXT", system_text)

    def test_temperature_retry_failure_raises(self):
        runner = MagicMock(side_effect=[ValueError("temperature unsupported"), ValueError("still broken")])
        with (
            patch.multiple(
                "apps.system_intelligence.services.public_assistant.invoke",
                run_tool_free_agent=runner,
                AWSCredentialConfig=MagicMock(),
            ),
            self.assertRaises(BedrockError),
        ):
            invoke.answer_public_question(config=_config(), message="hi", history=[], context="x")

    def test_non_temperature_error_raises(self):
        runner = MagicMock(side_effect=RuntimeError("network down"))
        with (
            patch.multiple(
                "apps.system_intelligence.services.public_assistant.invoke",
                run_tool_free_agent=runner,
                AWSCredentialConfig=MagicMock(),
            ),
            self.assertRaises(BedrockError),
        ):
            invoke.answer_public_question(config=_config(), message="hi", history=[], context="x")
