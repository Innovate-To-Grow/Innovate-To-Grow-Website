"""Unit tests for the tool-free Bedrock invocation service."""

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


def _response(text="hello", usage=None):
    body = {"output": {"message": {"content": [{"text": text}]}}}
    if usage is not None:
        body["usage"] = usage
    return body


class InvokeTests(TestCase):
    def _patch_client(self, mock_client):
        return patch.multiple(
            "apps.system_intelligence.services.public_assistant.invoke",
            get_client=MagicMock(return_value=mock_client),
            AWSCredentialConfig=MagicMock(),
        )

    def test_no_model_raises(self):
        with self.assertRaises(BedrockError):
            invoke.answer_public_question(
                config=_config(public_assistant_model_id="", default_model_id=""),
                message="hi",
                history=[],
                context="",
            )

    def test_history_roles_coerced_and_message_appended(self):
        mock_client = MagicMock()
        mock_client.converse.return_value = _response(
            "ans", usage={"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}
        )
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "system", "content": "dropped"},  # invalid role dropped
            {"role": "user", "content": "   "},  # blank dropped
            "not-a-dict",  # ignored
        ]
        with self._patch_client(mock_client):
            invoke.answer_public_question(config=_config(), message="newest", history=history, context="ctx")
        sent_messages = mock_client.converse.call_args.kwargs["messages"]
        self.assertEqual(len(sent_messages), 3)  # 2 valid history + new message
        self.assertEqual(sent_messages[-1], {"role": "user", "content": [{"text": "newest"}]})
        self.assertEqual(sent_messages[0]["content"][0]["text"], "first")

    def test_usage_estimated_when_missing(self):
        mock_client = MagicMock()
        mock_client.converse.return_value = _response("a" * 40, usage=None)
        with self._patch_client(mock_client):
            result = invoke.answer_public_question(config=_config(), message="question", history=[], context="x")
        self.assertGreater(result["usage"]["outputTokens"], 0)
        self.assertEqual(
            result["usage"]["totalTokens"],
            result["usage"]["inputTokens"] + result["usage"]["outputTokens"],
        )

    def test_estimate_includes_history_tokens(self):
        # The input estimate must count history turns, not just system + message,
        # so the per-IP budget is not under-charged when prior turns are present.
        mock_client = MagicMock()
        mock_client.converse.return_value = _response("ans", usage=None)
        long_history = [{"role": "user", "content": "h" * 4000}, {"role": "assistant", "content": "r" * 4000}]
        with self._patch_client(mock_client):
            with_hist = invoke.answer_public_question(config=_config(), message="q", history=long_history, context="x")
            without_hist = invoke.answer_public_question(config=_config(), message="q", history=[], context="x")
        self.assertGreater(with_hist["usage"]["inputTokens"], without_hist["usage"]["inputTokens"])

    def test_leading_assistant_history_dropped(self):
        # Bedrock requires the transcript to begin with a user turn; a leading
        # assistant turn from a hostile client must be dropped, not forwarded.
        mock_client = MagicMock()
        mock_client.converse.return_value = _response("ans", usage={"totalTokens": 2})
        history = [{"role": "assistant", "content": "I am the assistant"}]
        with self._patch_client(mock_client):
            invoke.answer_public_question(config=_config(), message="hi", history=history, context="x")
        sent = mock_client.converse.call_args.kwargs["messages"]
        self.assertEqual(sent[0]["role"], "user")
        self.assertTrue(all(m["role"] != "assistant" or i > 0 for i, m in enumerate(sent)))

    def test_consecutive_same_role_collapsed(self):
        # Two consecutive user turns would be rejected by Bedrock; they must be
        # collapsed so roles strictly alternate and end on a user turn.
        mock_client = MagicMock()
        mock_client.converse.return_value = _response("ans", usage={"totalTokens": 2})
        history = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
        with self._patch_client(mock_client):
            invoke.answer_public_question(config=_config(), message="c", history=history, context="x")
        roles = [m["role"] for m in mock_client.converse.call_args.kwargs["messages"]]
        # No two adjacent roles are equal, and it ends on a user turn.
        self.assertTrue(all(roles[i] != roles[i + 1] for i in range(len(roles) - 1)))
        self.assertEqual(roles[-1], "user")

    def test_empty_context_omits_dangling_header(self):
        mock_client = MagicMock()
        mock_client.converse.return_value = _response("ans", usage={"totalTokens": 2})
        with self._patch_client(mock_client):
            invoke.answer_public_question(config=_config(), message="hi", history=[], context="")
        system_text = mock_client.converse.call_args.kwargs["system"][0]["text"]
        self.assertNotIn("CONTEXT:", system_text)

    def test_temperature_error_detected_in_cause_chain(self):
        # The retry detection walks the exception chain, not just str(exc).
        mock_client = MagicMock()
        wrapped = RuntimeError("request failed")
        wrapped.__cause__ = ValueError("ValidationException: temperature not supported")
        good = _response("ok", usage={"totalTokens": 2})
        mock_client.converse.side_effect = [wrapped, good]
        with self._patch_client(mock_client):
            result = invoke.answer_public_question(config=_config(), message="hi", history=[], context="x")
        self.assertEqual(result["text"], "ok")
        self.assertEqual(mock_client.converse.call_count, 2)

    def test_context_built_when_not_provided(self):
        mock_client = MagicMock()
        mock_client.converse.return_value = _response(
            "ans", usage={"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}
        )
        with (
            self._patch_client(mock_client),
            patch.object(invoke, "build_public_context", return_value="GENERATED CONTEXT") as mock_ctx,
        ):
            invoke.answer_public_question(config=_config(), message="hi", history=[])
        mock_ctx.assert_called_once()
        system_text = mock_client.converse.call_args.kwargs["system"][0]["text"]
        self.assertIn("GENERATED CONTEXT", system_text)

    def test_temperature_retry_on_validation_error(self):
        mock_client = MagicMock()
        good = _response("ok", usage={"inputTokens": 1, "outputTokens": 1, "totalTokens": 2})
        mock_client.converse.side_effect = [
            ValueError("ValidationException: temperature is not supported"),
            good,
        ]
        with self._patch_client(mock_client):
            result = invoke.answer_public_question(config=_config(), message="hi", history=[], context="x")
        self.assertEqual(result["text"], "ok")
        self.assertEqual(mock_client.converse.call_count, 2)
        # Retry call omits temperature.
        retry_inference = mock_client.converse.call_args.kwargs["inferenceConfig"]
        self.assertNotIn("temperature", retry_inference)

    def test_temperature_retry_failure_raises(self):
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            ValueError("temperature unsupported"),
            ValueError("still broken"),
        ]
        with self._patch_client(mock_client), self.assertRaises(BedrockError):
            invoke.answer_public_question(config=_config(), message="hi", history=[], context="x")

    def test_non_temperature_error_raises(self):
        mock_client = MagicMock()
        mock_client.converse.side_effect = RuntimeError("network down")
        with self._patch_client(mock_client), self.assertRaises(BedrockError):
            invoke.answer_public_question(config=_config(), message="hi", history=[], context="x")
