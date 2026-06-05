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
