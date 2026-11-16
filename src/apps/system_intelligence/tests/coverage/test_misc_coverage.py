"""Coverage for the system_intelligence "misc" batch: admin/ + models/ + apps.py.

Targets the specific uncovered branches in admin/stream.py, admin/stream_helpers.py,
admin/commands/__init__.py, admin/actions/lookup.py,
apps.py, and the model __str__/property helpers.
"""

import json

from django.test import SimpleTestCase
from django.urls import reverse

from apps.system_intelligence.admin.stream.helpers import (
    _handle_stream_event,
    _stream_exception,
    _tool_calls_for_storage,
)
from apps.system_intelligence.models import (
    ChatMessage,
)
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class _FakeAwsConfig:
    """Minimal stand-in carrying just the attributes the helpers read."""

    def __init__(self, default_region=""):
        self.default_region = default_region


# ---------------------------------------------------------------------------
# admin/stream_helpers.py
# ---------------------------------------------------------------------------


class ToolCallsForStorageTests(SimpleTestCase):
    def test_non_dict_events_are_skipped(self):
        # Line 26: the non-dict event is dropped entirely.
        result = _tool_calls_for_storage(["not-a-dict", {"name": "search"}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "search")

    def test_non_dict_tool_input_is_coerced_to_empty_dict(self):
        # Line 29: input present but not a dict -> replaced with {}.
        result = _tool_calls_for_storage([{"name": "search", "input": "oops"}])
        self.assertEqual(result, [{"name": "search", "input": {}, "result_preview": ""}])

    def test_dict_input_and_preview_are_preserved(self):
        result = _tool_calls_for_storage([{"name": "search", "input": {"q": "Ada"}, "result_preview": "1 row"}])
        self.assertEqual(result[0]["input"], {"q": "Ada"})
        self.assertEqual(result[0]["result_preview"], "1 row")


class HandleStreamEventTests(SimpleTestCase):
    def test_unknown_event_type_returns_empty_payload_without_stopping(self):
        # Line 60: an unrecognised event type yields no SSE payload, no stop.
        chunk = _handle_stream_event(
            {"type": "mystery"},
            aws_config=_FakeAwsConfig(),
            full_text="kept",
            tool_calls=[],
            action_ids=[],
            action_requests=[],
            total_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        )
        self.assertEqual(chunk, {"full_text": "kept", "payload": "", "stop": False})


class StreamExceptionTests(SimpleTestCase):
    def test_bedrock_connectivity_error_uses_validated_region(self):
        # Lines 73-85: connectivity error path with a region that matches the regex.
        exc = RuntimeError(
            "litellm.ServiceUnavailableError: BedrockException - Cannot connect to host "
            "bedrock-runtime.example.amazonaws.com:443 [Could not contact DNS servers]"
        )
        with self.assertLogs("apps.system_intelligence.admin.stream.helpers", level="WARNING") as logs:
            payload = _stream_exception("conv-1", exc, _FakeAwsConfig(default_region="us-west-2"))
        self.assertIn("event: error", payload)
        self.assertIn("Unable to reach AWS Bedrock Runtime in us-west-2", payload)
        # The raw exception text must never leak into the response.
        self.assertNotIn("litellm", payload)
        self.assertIn("region us-west-2", "\n".join(logs.output))

    def test_bedrock_connectivity_error_with_invalid_region_falls_back(self):
        # Line 76: region that fails the regex is replaced with the placeholder.
        exc = RuntimeError("BedrockException: could not contact dns servers")
        with self.assertLogs("apps.system_intelligence.admin.stream.helpers", level="WARNING"):
            payload = _stream_exception("conv-2", exc, _FakeAwsConfig(default_region="NOT-A-REGION"))
        self.assertIn("Unable to reach AWS Bedrock Runtime in the configured region", payload)

    def test_generic_error_uses_generic_message_and_logs_exception(self):
        # Lines 86-89: a non-connectivity error gets the generic message and an
        # exception-level log entry.
        exc = ValueError("internal boom with secrets")
        with self.assertLogs("apps.system_intelligence.admin.stream.helpers", level="ERROR") as logs:
            payload = _stream_exception("conv-3", exc, _FakeAwsConfig())
        self.assertIn("could not complete this turn", payload)
        self.assertNotIn("secrets", payload)
        self.assertIn("Stream error for conversation conv-3", "\n".join(logs.output))


# ---------------------------------------------------------------------------
# admin/stream.py (chat_send_view guards + _event_stream branches)
# ---------------------------------------------------------------------------


class ChatSendViewGuardTests(SystemIntelligenceAdminBase):
    def _url(self):
        return reverse("admin:system_intelligence_send", args=[self.conversation.id])

    def test_non_post_returns_405(self):
        # Line 28.
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "POST required")

    def test_unknown_conversation_returns_404(self):
        # Lines 31-32: the lookup raises DoesNotExist.
        import uuid

        response = self.client.post(
            reverse("admin:system_intelligence_send", args=[uuid.uuid4()]),
            data=json.dumps({"message": "hi"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Conversation not found")

    def test_invalid_json_body_returns_400(self):
        # Lines 35-36: json.loads raises JSONDecodeError.
        response = self.client.post(self._url(), data="not-json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON body")

    def test_empty_message_returns_400(self):
        # Line 38: whitespace-only message is rejected.
        response = self.client.post(self._url(), data=json.dumps({"message": "   "}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Message cannot be empty")
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation).exists())


# ---------------------------------------------------------------------------
# admin/commands/__init__.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# admin/actions/lookup.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# apps.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# models __str__ / property helpers
# ---------------------------------------------------------------------------
