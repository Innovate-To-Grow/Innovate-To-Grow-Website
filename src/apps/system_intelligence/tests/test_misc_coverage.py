"""Coverage for the system_intelligence "misc" batch: admin/ + models/ + apps.py.

Targets the specific uncovered branches in admin/stream.py, admin/stream_helpers.py,
admin/commands/__init__.py, admin/actions/lookup.py, admin/actions/rendering.py,
apps.py, and the model __str__/property helpers.
"""

import json
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from django.urls import reverse

from apps.system_intelligence.admin.actions.lookup import (
    _changed_preview_blocks,
    _cms_preview_page,
    _get_user_action_request,
)
from apps.system_intelligence.admin.stream_helpers import (
    _handle_stream_event,
    _stream_exception,
    _tool_calls_for_storage,
)
from apps.system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
    SystemIntelligenceExport,
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
        with self.assertLogs("apps.system_intelligence.admin.stream_helpers", level="WARNING") as logs:
            payload = _stream_exception("conv-1", exc, _FakeAwsConfig(default_region="us-west-2"))
        self.assertIn("event: error", payload)
        self.assertIn("Unable to reach AWS Bedrock Runtime in us-west-2", payload)
        # The raw exception text must never leak into the response.
        self.assertNotIn("litellm", payload)
        self.assertIn("region us-west-2", "\n".join(logs.output))

    def test_bedrock_connectivity_error_with_invalid_region_falls_back(self):
        # Line 76: region that fails the regex is replaced with the placeholder.
        exc = RuntimeError("BedrockException: could not contact dns servers")
        with self.assertLogs("apps.system_intelligence.admin.stream_helpers", level="WARNING"):
            payload = _stream_exception("conv-2", exc, _FakeAwsConfig(default_region="NOT-A-REGION"))
        self.assertIn("Unable to reach AWS Bedrock Runtime in the configured region", payload)

    def test_generic_error_uses_generic_message_and_logs_exception(self):
        # Lines 86-89: a non-connectivity error gets the generic message and an
        # exception-level log entry.
        exc = ValueError("internal boom with secrets")
        with self.assertLogs("apps.system_intelligence.admin.stream_helpers", level="ERROR") as logs:
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


class EventStreamBranchTests(SystemIntelligenceAdminBase):
    def _url(self):
        return reverse("admin:system_intelligence_send", args=[self.conversation.id])

    def test_prepared_context_error_short_circuits_stream(self):
        # Lines 103-104: prepared_context.error yields an SSE error and stops
        # before the model is ever invoked, so no assistant message persists.
        class _Prepared:
            usage = {}
            error = "context build failed"
            messages = []

        with (
            patch(
                "apps.system_intelligence.admin.stream.prepare_conversation_context",
                return_value=_Prepared(),
            ),
            patch("apps.system_intelligence.admin.invoke_system_intelligence_stream") as stream,
        ):
            response = self.client.post(
                self._url(),
                data=json.dumps({"message": "hello"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertIn("event: error", body)
        self.assertIn("context build failed", body)
        stream.assert_not_called()
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation, role="assistant").exists())

    def test_stream_exception_is_caught_and_rendered_as_sse_error(self):
        # Lines 123-125: an exception raised while iterating the model stream is
        # caught and converted to a sanitized SSE error.
        def _boom(*args, **kwargs):
            raise RuntimeError("secret internal detail")

        with patch(
            "apps.system_intelligence.admin.invoke_system_intelligence_stream",
            side_effect=_boom,
        ):
            with self.assertLogs("apps.system_intelligence.admin.stream_helpers", level="ERROR"):
                response = self.client.post(
                    self._url(),
                    data=json.dumps({"message": "hello"}),
                    content_type="application/json",
                )
                body = b"".join(response.streaming_content).decode()

        self.assertIn("event: error", body)
        self.assertIn("could not complete this turn", body)
        self.assertNotIn("secret internal detail", body)
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation, role="assistant").exists())


# ---------------------------------------------------------------------------
# admin/commands/__init__.py
# ---------------------------------------------------------------------------


class ChatCommandViewGuardTests(SystemIntelligenceAdminBase):
    def _url(self, conversation_id=None):
        return reverse(
            "admin:system_intelligence_command",
            args=[conversation_id or self.conversation.id],
        )

    def test_non_post_returns_405(self):
        # Line 26.
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "POST required")

    def test_unknown_conversation_returns_404(self):
        # Lines 29-30.
        import uuid

        response = self.client.post(
            self._url(uuid.uuid4()),
            data=json.dumps({"command": "title", "args": "x"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Conversation not found")

    def test_invalid_json_body_returns_400(self):
        # Lines 33-34.
        response = self.client.post(self._url(), data="{bad json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON body")

    def test_compact_returns_400_when_aws_not_configured(self):
        # Line 81: enough older messages but AWS credentials are missing.
        for index in range(30):
            ChatMessage.objects.create(
                conversation=self.conversation,
                role="user" if index % 2 == 0 else "assistant",
                content=f"message {index}",
            )

        class _Unconfigured:
            is_configured = False

        with (
            patch(
                "apps.system_intelligence.admin.commands.AWSCredentialConfig.load",
                return_value=_Unconfigured(),
            ),
            patch("apps.system_intelligence.admin.commands.ensure_context_summary") as summarize,
        ):
            response = self.client.post(
                self._url(),
                data=json.dumps({"command": "compact"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "AWS credentials are not configured.")
        summarize.assert_not_called()

    def test_retry_with_only_assistant_messages_returns_400(self):
        # Lines 118-123: every trailing assistant turn is removed, leaving no
        # user message to retry.
        ChatMessage.objects.create(conversation=self.conversation, role="assistant", content="orphan")
        with patch("apps.system_intelligence.admin.invoke_system_intelligence_stream") as stream:
            response = self.client.post(
                self._url(),
                data=json.dumps({"command": "retry"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "No user message to retry.")
        stream.assert_not_called()
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation).exists())


# ---------------------------------------------------------------------------
# admin/actions/lookup.py
# ---------------------------------------------------------------------------


class CmsPreviewPageTests(SystemIntelligenceAdminBase):
    def test_non_cms_action_returns_none(self):
        # Line 19: only CMS page update actions have a previewable page.
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            title="Not a CMS change",
        )
        self.assertIsNone(_cms_preview_page(action))


class ChangedPreviewBlocksTests(SimpleTestCase):
    def test_non_dict_after_blocks_are_skipped(self):
        # Line 38: an after-block that is not a dict is ignored.
        action = SystemIntelligenceActionRequest(before_snapshot={"blocks": []})
        page = {"blocks": ["not-a-dict", {"block_type": "rich_text", "id": "1"}]}
        changed = _changed_preview_blocks(action, page)
        self.assertEqual(changed, [{"block_type": "rich_text", "id": "1"}])


class GetUserActionRequestTests(SystemIntelligenceAdminBase):
    def test_missing_action_raises_permission_denied(self):
        import uuid

        request = type("R", (), {"user": self.admin_user})()
        with self.assertRaises(PermissionDenied):
            _get_user_action_request(request, uuid.uuid4())


# ---------------------------------------------------------------------------
# apps.py
# ---------------------------------------------------------------------------


class AppReadyIdempotencyTests(SimpleTestCase):
    def test_ready_is_idempotent_when_urls_already_patched(self):
        # Line 17: the app config has already run ready() during startup, so the
        # admin site carries the patched flag. Calling ready() again must take
        # the early-return path and leave get_urls untouched.
        app_config = django_apps.get_app_config("system_intelligence")
        self.assertTrue(getattr(admin.AdminSite, "_system_intelligence_urls_patched", False))
        before = admin.AdminSite.get_urls
        app_config.ready()
        self.assertIs(admin.AdminSite.get_urls, before)


# ---------------------------------------------------------------------------
# models __str__ / property helpers
# ---------------------------------------------------------------------------


class ModelStrTests(SystemIntelligenceAdminBase):
    def test_chat_conversation_str(self):
        # chat.py line 50.
        convo = ChatConversation.objects.create(title="Roadmap", created_by=self.admin_user)
        self.assertEqual(str(convo), f"Roadmap ({self.admin_user})")

    def test_chat_message_str_truncates_long_content(self):
        # chat.py lines 93-94 (truncating branch).
        long = "x" * 80
        message = ChatMessage.objects.create(conversation=self.conversation, role="assistant", content=long)
        self.assertEqual(str(message), f"[assistant] {'x' * 60}...")

    def test_chat_message_str_keeps_short_content(self):
        # chat.py lines 93-94 (non-truncating branch).
        message = ChatMessage.objects.create(conversation=self.conversation, role="user", content="short")
        self.assertEqual(str(message), "[user] short")

    def test_action_request_str(self):
        # actions.py line 89.
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_CREATE,
            status=SystemIntelligenceActionRequest.STATUS_PENDING,
            title="Add row",
        )
        self.assertEqual(str(action), "Database create: Add row [pending]")

    def test_export_str(self):
        # export.py line 43.
        export = SystemIntelligenceExport.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            filename="members.xlsx",
            title="Members",
            row_count=42,
        )
        self.assertEqual(str(export), "Members (42 rows)")


class ConfigModelTests(SystemIntelligenceAdminBase):
    def test_str_marks_active_config(self):
        # config.py lines 54-55 (active branch).
        config = SystemIntelligenceConfig(name="Primary", is_active=True)
        self.assertEqual(str(config), "Primary (active)")

    def test_str_omits_marker_for_inactive_config(self):
        # config.py lines 54-55 (inactive branch).
        config = SystemIntelligenceConfig(name="Backup", is_active=False)
        self.assertEqual(str(config), "Backup")

    def test_is_configured_is_always_true(self):
        # config.py line 71.
        self.assertTrue(SystemIntelligenceConfig().is_configured)
