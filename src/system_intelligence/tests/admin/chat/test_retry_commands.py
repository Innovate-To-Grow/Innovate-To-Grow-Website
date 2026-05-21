import json
from unittest.mock import patch

from django.urls import reverse

from system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
)
from system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


def _command_url(conversation_id):
    return reverse("admin:system_intelligence_command", args=[conversation_id])


class SystemIntelligenceCommandTests(SystemIntelligenceAdminBase):
    def test_retry_command_drops_trailing_assistant_and_re_streams(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Find Ada")
        prior_assistant = ChatMessage.objects.create(
            conversation=self.conversation, role="assistant", content="Found nothing."
        )
        with patch(
            "system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "text", "chunk": "Retry attempt."}]),
        ) as stream:
            response = self.client.post(
                _command_url(self.conversation.id),
                data=json.dumps({"command": "retry"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Retry attempt.", body)
        # The previous assistant turn is removed so prepare_conversation_context sees a trailing user message.
        self.assertFalse(ChatMessage.objects.filter(pk=prior_assistant.pk).exists())
        self.assertEqual(stream.call_args.args[0][-1], {"role": "user", "content": "Find Ada"})

    def test_retry_rejects_pending_actions_attached_to_dropped_assistant_turn(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Add feed")
        prior_assistant = ChatMessage.objects.create(
            conversation=self.conversation, role="assistant", content="Proposed."
        )
        pending_action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            assistant_message=prior_assistant,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_CREATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            title="Create feed",
            summary="",
        )
        with patch(
            "system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "text", "chunk": "Retry attempt."}]),
        ):
            response = self.client.post(
                _command_url(self.conversation.id),
                data=json.dumps({"command": "retry"}),
                content_type="application/json",
            )
            b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        pending_action.refresh_from_db()
        self.assertEqual(pending_action.status, SystemIntelligenceActionRequest.STATUS_REJECTED)
        self.assertIsNone(pending_action.assistant_message_id)
        self.assertIsNotNone(pending_action.reviewed_at)

    def test_retry_command_with_no_messages_returns_400(self):
        response = self.client.post(
            _command_url(self.conversation.id),
            data=json.dumps({"command": "retry"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Nothing to retry", response.json()["error"])

    def test_conversation_payload_exposes_mode(self):
        self.conversation.mode = ChatConversation.MODE_PLAN
        self.conversation.save(update_fields=["mode"])
        detail = self.client.get(reverse("admin:system_intelligence_detail", args=[self.conversation.id]))
        self.assertEqual(detail.json()["mode"], "plan")
        listing = self.client.get(reverse("admin:system_intelligence_conversations"))
        self.assertEqual(listing.json()["conversations"][0]["mode"], "plan")
