from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.system_intelligence.services.bedrock.clients.exceptions import BedrockError
from apps.system_intelligence.services.bedrock.invoke.streaming import invoke_bedrock_stream
from apps.system_intelligence.tests.services.bedrock.test_invoke import _client_error


class InvokeBedrockStreamTest(SimpleTestCase):
    def test_prepare_error_yields_error_event(self):
        with patch(
            "apps.system_intelligence.services.bedrock.invoke.streaming.prepare",
            side_effect=BedrockError("nope"),
        ):
            events = list(invoke_bedrock_stream([{"role": "user", "content": "x"}]))
        self.assertEqual(events, [{"type": "error", "error": "nope"}])

    def test_client_error_yields_error_event(self):
        client = MagicMock()
        client.converse_stream.side_effect = _client_error()
        with patch(
            "apps.system_intelligence.services.bedrock.invoke.streaming.prepare",
            return_value=(client, [], {}),
        ):
            events = list(invoke_bedrock_stream([{"role": "user", "content": "x"}]))
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("Bedrock API error", events[0]["error"])

    def test_unexpected_error_yields_error_event(self):
        client = MagicMock()
        client.converse_stream.side_effect = RuntimeError("boom")
        with patch(
            "apps.system_intelligence.services.bedrock.invoke.streaming.prepare",
            return_value=(client, [], {}),
        ):
            events = list(invoke_bedrock_stream([{"role": "user", "content": "x"}]))
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("Unexpected error", events[0]["error"])

    def test_text_stream_then_end(self):
        client = MagicMock()
        client.converse_stream.return_value = {"stream": []}
        outcome = {
            "content_blocks": [{"text": "hi"}],
            "stop_reason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
        }

        def fake_process(_response):
            yield {"type": "text", "chunk": "hi"}
            return outcome

        with (
            patch("apps.system_intelligence.services.bedrock.invoke.streaming.prepare", return_value=(client, [], {})),
            patch(
                "apps.system_intelligence.services.bedrock.invoke.streaming.process_stream_response",
                side_effect=fake_process,
            ),
        ):
            events = list(invoke_bedrock_stream([{"role": "user", "content": "x"}]))
        types = [e["type"] for e in events]
        self.assertIn("text", types)
        self.assertIn("usage", types)

    def test_tool_use_round_then_end(self):
        client = MagicMock()
        client.converse_stream.return_value = {"stream": []}
        outcome_tool = {
            "content_blocks": [{"toolUse": {"toolUseId": "t1", "name": "n", "input": {}}}],
            "stop_reason": "tool_use",
            "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        }
        outcome_end = {
            "content_blocks": [{"text": "fin"}],
            "stop_reason": "end_turn",
            "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        }
        outcomes = iter([outcome_tool, outcome_end])

        def fake_process_gen(_response):
            if False:
                yield
            return next(outcomes)

        with (
            patch("apps.system_intelligence.services.bedrock.invoke.streaming.prepare", return_value=(client, [], {})),
            patch(
                "apps.system_intelligence.services.bedrock.invoke.streaming.process_stream_response",
                side_effect=fake_process_gen,
            ),
            patch(
                "apps.system_intelligence.services.bedrock.invoke.streaming.stream_tool_results",
                return_value=[({"type": "tool_call", "name": "n"}, {"toolResult": {}})],
            ),
        ):
            events = list(invoke_bedrock_stream([{"role": "user", "content": "x"}]))
        types = [e["type"] for e in events]
        self.assertIn("tool_call", types)
        self.assertIn("usage", types)

    def test_too_many_tool_rounds(self):
        client = MagicMock()
        client.converse_stream.return_value = {"stream": []}
        outcome_tool = {
            "content_blocks": [{"toolUse": {"toolUseId": "t1", "name": "n", "input": {}}}],
            "stop_reason": "tool_use",
            "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        }

        def fake_process_gen(_response):
            if False:
                yield
            return outcome_tool

        with (
            patch("apps.system_intelligence.services.bedrock.invoke.streaming.prepare", return_value=(client, [], {})),
            patch(
                "apps.system_intelligence.services.bedrock.invoke.streaming.process_stream_response",
                side_effect=fake_process_gen,
            ),
            patch(
                "apps.system_intelligence.services.bedrock.invoke.streaming.stream_tool_results",
                return_value=[],
            ),
        ):
            events = list(invoke_bedrock_stream([{"role": "user", "content": "x"}]))
        self.assertEqual(events[-1], {"type": "error", "error": "Too many tool-use rounds."})
