import json
from unittest.mock import patch

from django.urls import reverse

from apps.system_intelligence.admin.actions.lookup import (
    _cms_preview_page,
)
from apps.system_intelligence.models import (
    ChatMessage,
    LLMProviderConfig,
    SystemIntelligenceActionRequest,
)
from apps.system_intelligence.services.agents.providers.routing import NO_AWS
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


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
                "apps.system_intelligence.admin.stream.sync_events.prepare_conversation_context",
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
            with self.assertLogs("apps.system_intelligence.admin.stream.helpers", level="ERROR"):
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

    def _compact_without_aws(self):
        for index in range(30):
            ChatMessage.objects.create(
                conversation=self.conversation, role="user" if index % 2 == 0 else "assistant", content=f"m {index}"
            )
        unconfigured = type("_Unconfigured", (), {"is_configured": False})()
        with (
            patch("apps.system_intelligence.admin.chat.commands.AWSCredentialConfig.load", return_value=unconfigured),
            patch(
                "apps.system_intelligence.admin.chat.commands.ensure_context_summary", return_value=("s", {})
            ) as summarize,
        ):
            response = self.client.post(
                self._url(), data=json.dumps({"command": "compact"}), content_type="application/json"
            )
        return response, summarize

    def test_compact_returns_400_when_aws_not_configured(self):
        # Enough older messages, Bedrock route, but AWS credentials are missing.
        response, summarize = self._compact_without_aws()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], NO_AWS)
        summarize.assert_not_called()

    def test_compact_returns_400_when_the_provider_is_disabled(self):
        self.chat_config.default_provider = LLMProviderConfig.objects.create(name="DeepSeek", preset="deepseek")
        self.chat_config.save()
        response, summarize = self._compact_without_aws()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], 'The AI provider "DeepSeek" is disabled.')
        summarize.assert_not_called()

    def test_compact_with_a_ready_provider_does_not_need_aws(self):
        self.chat_config.default_provider = LLMProviderConfig.objects.create(
            name="DeepSeek", preset="deepseek", is_enabled=True, key_secret_ref="memory:k", key_version_id="v1"
        )
        self.chat_config.save()
        response, summarize = self._compact_without_aws()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["compacted"])
        summarize.assert_called_once()

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
