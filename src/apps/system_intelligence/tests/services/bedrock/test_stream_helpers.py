from unittest.mock import patch

from django.test import SimpleTestCase

from apps.system_intelligence.services.bedrock.invoke.stream_parser import (
    process_stream_response,
    start_content_block,
    stop_content_block,
    stream_tool_results,
)


class StreamHelpersTest(SimpleTestCase):
    def test_process_stream_response_text_and_metadata(self):
        response = {
            "stream": [
                {"contentBlockStart": {"start": {}}},
                {"contentBlockDelta": {"delta": {"text": "Hel"}}},
                {"contentBlockDelta": {"delta": {"text": "lo"}}},
                {"contentBlockStop": {}},
                {"messageStop": {"stopReason": "end_turn"}},
                {
                    "metadata": {
                        "usage": {
                            "inputTokens": 3,
                            "outputTokens": 5,
                            "totalTokens": 8,
                            "cacheReadInputTokens": 4,
                            "cacheWriteInputTokens": 2,
                        }
                    }
                },
            ]
        }
        gen = process_stream_response(response)
        chunks = list(gen)
        # generator yields text chunks then returns outcome via StopIteration.value
        self.assertEqual(chunks, [{"type": "text", "chunk": "Hel"}, {"type": "text", "chunk": "lo"}])
        # Re-run to capture the return value
        outcome = self._drain(process_stream_response(response))
        self.assertEqual(outcome["stop_reason"], "end_turn")
        self.assertEqual(
            outcome["usage"],
            {
                "inputTokens": 3,
                "outputTokens": 5,
                "totalTokens": 8,
                "cacheReadInputTokens": 4,
                "cacheWriteInputTokens": 2,
            },
        )
        self.assertEqual(outcome["content_blocks"], [{"text": "Hello"}])

    def test_process_stream_response_tool_use(self):
        response = {
            "stream": [
                {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": "fn"}}}},
                {"contentBlockDelta": {"delta": {"toolUse": {"input": '{"a":'}}}},
                {"contentBlockDelta": {"delta": {"toolUse": {"input": "1}"}}}},
                {"contentBlockStop": {}},
                {"messageStop": {"stopReason": "tool_use"}},
            ]
        }
        outcome = self._drain(process_stream_response(response))
        self.assertEqual(outcome["stop_reason"], "tool_use")
        block = outcome["content_blocks"][0]
        self.assertEqual(block["toolUse"]["input"], {"a": 1})
        self.assertEqual(block["toolUse"]["name"], "fn")

    def test_start_content_block_text(self):
        block, buf = start_content_block({"contentBlockStart": {"start": {}}})
        self.assertEqual(block, {"type": "text", "text": ""})
        self.assertEqual(buf, "")

    def test_start_content_block_tool(self):
        block, buf = start_content_block(
            {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t9", "name": "z"}}}}
        )
        self.assertEqual(block["type"], "toolUse")
        self.assertEqual(block["toolUseId"], "t9")
        self.assertEqual(buf, "")

    def test_stop_content_block_invalid_json_defaults_empty(self):
        block = stop_content_block({"type": "toolUse", "toolUseId": "t", "name": "n"}, "not-json")
        self.assertEqual(block["toolUse"]["input"], {})

    def test_stop_content_block_text(self):
        block = stop_content_block({"type": "text", "text": "abc"}, "")
        self.assertEqual(block, {"text": "abc"})

    def test_stream_tool_results_yields_events_and_results(self):
        blocks = [
            {"text": "ignored"},
            {"toolUse": {"toolUseId": "t1", "name": "do_it", "input": {"k": "v"}}},
        ]
        with patch(
            "apps.system_intelligence.services.bedrock.invoke.stream_parser.execute_tool",
            return_value="Z" * 250,
        ):
            outputs = list(stream_tool_results(blocks, round_num=2))
        self.assertEqual(len(outputs), 1)
        event, result = outputs[0]
        self.assertEqual(event["type"], "tool_call")
        self.assertEqual(event["name"], "do_it")
        self.assertEqual(len(event["result_preview"]), 200)
        self.assertEqual(result["toolResult"]["toolUseId"], "t1")

    @staticmethod
    def _drain(gen):
        """Exhaust a generator and return the value carried by StopIteration."""
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            return stop.value
