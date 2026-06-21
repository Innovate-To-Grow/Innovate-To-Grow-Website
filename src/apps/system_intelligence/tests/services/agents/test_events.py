from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.system_intelligence.services.agents import _normalize_agent_stream_event, _StreamState, _usage_event


class SystemIntelligenceAgentEventTests(SimpleTestCase):
    def test_raw_text_delta_streams_incremental_text(self):
        state = _StreamState()
        event = SimpleNamespace(
            type="raw_response_event",
            data=SimpleNamespace(type="response.output_text.delta", delta="Hello"),
        )

        self.assertEqual(_normalize_agent_stream_event(event, state), [{"type": "text", "chunk": "Hello"}])
        self.assertEqual(state.streamed_text, "Hello")

    def test_message_output_does_not_duplicate_streamed_delta(self):
        state = _StreamState()
        state.streamed_text = "Hel"
        event = SimpleNamespace(
            type="run_item_stream_event",
            name="message_output_created",
            item=SimpleNamespace(
                type="message_output_item",
                raw_item=SimpleNamespace(content=[SimpleNamespace(text="Hello")]),
            ),
        )

        self.assertEqual(_normalize_agent_stream_event(event, state), [{"type": "text", "chunk": "lo"}])

    def test_tool_output_emits_tool_and_action_request_events(self):
        state = _StreamState()
        call = SimpleNamespace(
            type="run_item_stream_event",
            name="tool_called",
            item=SimpleNamespace(
                type="tool_call_item",
                raw_item=SimpleNamespace(call_id="call-1", name="propose_db_update", arguments='{"pk": "1"}'),
            ),
        )
        response = SimpleNamespace(
            type="run_item_stream_event",
            name="tool_output",
            item=SimpleNamespace(
                type="tool_call_output_item",
                raw_item=SimpleNamespace(call_id="call-1"),
                output={
                    "result": "Created request",
                    "action_request": {"id": "action-1", "title": "Update", "status": "pending"},
                },
            ),
        )

        self.assertEqual(_normalize_agent_stream_event(call, state), [])
        self.assertEqual(
            _normalize_agent_stream_event(response, state),
            [
                {
                    "type": "tool_call",
                    "name": "propose_db_update",
                    "input": {"pk": "1"},
                    "result_preview": "Created request",
                },
                {"type": "action_request", "id": "action-1", "title": "Update", "status": "pending"},
            ],
        )

    @staticmethod
    def _message_output(text):
        return SimpleNamespace(
            type="run_item_stream_event",
            name="message_output_created",
            item=SimpleNamespace(
                type="message_output_item",
                raw_item=SimpleNamespace(content=[SimpleNamespace(text=text)]),
            ),
        )

    def test_message_output_emits_full_text_when_no_deltas_were_streamed(self):
        # Provider never emitted response.output_text.delta -> message_output is the only source.
        state = _StreamState()
        self.assertEqual(
            _normalize_agent_stream_event(self._message_output("Full answer"), state),
            [{"type": "text", "chunk": "Full answer"}],
        )
        self.assertEqual(state.streamed_text, "Full answer")

    def test_message_output_is_suppressed_when_fully_streamed(self):
        state = _StreamState()
        state.streamed_text = "Hello world"
        self.assertEqual(_normalize_agent_stream_event(self._message_output("Hello world"), state), [])

    def test_message_output_after_tool_call_is_not_dropped(self):
        # Regression: a second message whose text does not share the accumulated prefix
        # must still be delivered (the old removeprefix logic silently dropped it).
        state = _StreamState()
        state.streamed_text = "First answer."
        self.assertEqual(
            _normalize_agent_stream_event(self._message_output("Second answer."), state),
            [{"type": "text", "chunk": "Second answer."}],
        )
        self.assertEqual(state.streamed_text, "First answer.Second answer.")

    def test_message_output_emits_divergent_extension(self):
        state = _StreamState()
        state.streamed_text = "Hello"
        self.assertEqual(
            _normalize_agent_stream_event(self._message_output("Hello world"), state),
            [{"type": "text", "chunk": " world"}],
        )

    def test_usage_event_maps_agents_usage_to_existing_shape(self):
        usage = SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14)

        self.assertEqual(
            _usage_event(usage),
            {"type": "usage", "inputTokens": 10, "outputTokens": 4, "totalTokens": 14},
        )
