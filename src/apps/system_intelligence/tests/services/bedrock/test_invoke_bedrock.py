from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.system_intelligence.services.bedrock.clients.exceptions import BedrockError
from apps.system_intelligence.services.bedrock.invoke.converse import collect_tool_results, invoke_bedrock
from apps.system_intelligence.tests.services.bedrock.test_invoke import _client_error


class InvokeBedrockTest(SimpleTestCase):
    def _prep(self, client):
        return patch(
            "apps.system_intelligence.services.bedrock.invoke.converse.prepare",
            return_value=(client, [], {"modelId": "m"}),
        )

    def test_returns_text_on_end_turn(self):
        client = MagicMock()
        client.converse.return_value = {
            "output": {"message": {"role": "assistant", "content": [{"text": "Hi "}, {"text": "there"}]}},
            "stopReason": "end_turn",
        }
        with self._prep(client):
            result = invoke_bedrock([{"role": "user", "content": "hey"}])
        self.assertEqual(result["text"], "Hi there")
        self.assertEqual(result["tool_calls"], [])

    def test_tool_use_loop_then_final_text(self):
        client = MagicMock()
        tool_msg = {
            "role": "assistant",
            "content": [{"toolUse": {"toolUseId": "t1", "name": "get_stuff", "input": {"q": 1}}}],
        }
        final_msg = {"role": "assistant", "content": [{"text": "done"}]}
        client.converse.side_effect = [
            {"output": {"message": tool_msg}, "stopReason": "tool_use"},
            {"output": {"message": final_msg}, "stopReason": "end_turn"},
        ]
        with (
            self._prep(client),
            patch("apps.system_intelligence.services.bedrock.invoke.converse.execute_tool", return_value="RESULT"),
        ):
            result = invoke_bedrock([{"role": "user", "content": "hey"}])
        self.assertEqual(result["text"], "done")
        self.assertEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["name"], "get_stuff")
        self.assertEqual(result["tool_calls"][0]["result_preview"], "RESULT")

    def test_client_error_wrapped(self):
        client = MagicMock()
        client.converse.side_effect = _client_error()
        with self._prep(client), self.assertRaises(BedrockError) as cm:
            invoke_bedrock([{"role": "user", "content": "x"}])
        self.assertIn("Bedrock API error", str(cm.exception))

    def test_unexpected_error_wrapped(self):
        client = MagicMock()
        client.converse.side_effect = RuntimeError("kaboom")
        with self._prep(client), self.assertRaises(BedrockError) as cm:
            invoke_bedrock([{"role": "user", "content": "x"}])
        self.assertIn("Unexpected error", str(cm.exception))

    def test_exhausts_tool_rounds(self):
        client = MagicMock()
        tool_msg = {
            "role": "assistant",
            "content": [{"toolUse": {"toolUseId": "t1", "name": "loop", "input": {}}}],
        }
        client.converse.return_value = {"output": {"message": tool_msg}, "stopReason": "tool_use"}
        with (
            self._prep(client),
            patch("apps.system_intelligence.services.bedrock.invoke.converse.execute_tool", return_value="R"),
        ):
            result = invoke_bedrock([{"role": "user", "content": "x"}])
        self.assertIn("unable to complete the request", result["text"])
        self.assertEqual(len(result["tool_calls"]), 10)

    def test_collect_tool_results_skips_text_blocks(self):
        log = []
        output_message = {
            "content": [
                {"text": "ignore me"},
                {"toolUse": {"toolUseId": "t1", "name": "n", "input": {"a": 1}}},
            ]
        }
        with patch("apps.system_intelligence.services.bedrock.invoke.converse.execute_tool", return_value="X" * 300):
            results = collect_tool_results(output_message, log)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["toolResult"]["toolUseId"], "t1")
        self.assertEqual(len(log[0]["result_preview"]), 200)  # truncated to 200
