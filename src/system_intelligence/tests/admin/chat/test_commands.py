import json
from unittest.mock import patch

from django.urls import reverse

from system_intelligence.models import (
    ChatConversation,
    ChatMessage,
)
from system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


def _command_url(conversation_id):
    return reverse("admin:system_intelligence_command", args=[conversation_id])


class SystemIntelligenceCommandTests(SystemIntelligenceAdminBase):
    def test_plan_command_without_args_only_flips_mode(self):
        response = self.client.post(
            _command_url(self.conversation.id),
            data=json.dumps({"command": "plan"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], ChatConversation.MODE_PLAN)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.mode, ChatConversation.MODE_PLAN)
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation).exists())

    def test_plan_command_with_args_streams_in_plan_mode(self):
        with patch(
            "system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "text", "chunk": "Plan step 1."}]),
        ) as stream:
            response = self.client.post(
                _command_url(self.conversation.id),
                data=json.dumps({"command": "plan", "args": "Refresh the news feed"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn("Plan step 1.", body)
        self.assertEqual(stream.call_args.kwargs["mode"], ChatConversation.MODE_PLAN)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.mode, ChatConversation.MODE_PLAN)
        user_messages = ChatMessage.objects.filter(conversation=self.conversation, role="user")
        self.assertEqual(user_messages.count(), 1)
        self.assertEqual(user_messages.first().content, "Refresh the news feed")

    def test_exit_plan_command_clears_mode(self):
        self.conversation.mode = ChatConversation.MODE_PLAN
        self.conversation.save(update_fields=["mode"])
        response = self.client.post(
            _command_url(self.conversation.id),
            data=json.dumps({"command": "exit-plan"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], ChatConversation.MODE_NORMAL)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.mode, ChatConversation.MODE_NORMAL)

    def test_compact_command_invokes_summarizer_with_force(self):
        for index in range(30):
            ChatMessage.objects.create(
                conversation=self.conversation,
                role="user" if index % 2 == 0 else "assistant",
                content=f"message {index}",
            )

        with patch(
            "system_intelligence.admin.commands.ensure_context_summary",
            return_value=("summary text", {"summarized_messages": 4, "summary_failed": False}),
        ) as summarize:
            response = self.client.post(
                _command_url(self.conversation.id),
                data=json.dumps({"command": "compact"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["compacted"])
        self.assertEqual(payload["messages_summarized"], 4)
        self.assertTrue(summarize.call_args.kwargs["force"])

    def test_compact_command_returns_friendly_notice_when_too_short(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="hi")
        with patch("system_intelligence.admin.commands.ensure_context_summary") as summarize:
            response = self.client.post(
                _command_url(self.conversation.id),
                data=json.dumps({"command": "compact"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["compacted"])
        self.assertIn("Not enough", payload["message"])
        summarize.assert_not_called()

    def test_unknown_command_returns_400(self):
        response = self.client.post(
            _command_url(self.conversation.id),
            data=json.dumps({"command": "nope"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown command", response.json()["error"])

    def test_title_command_renames_conversation(self):
        response = self.client.post(
            _command_url(self.conversation.id),
            data=json.dumps({"command": "title", "args": "Roadmap planning"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Roadmap planning")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "Roadmap planning")

    def test_title_command_requires_args(self):
        response = self.client.post(
            _command_url(self.conversation.id),
            data=json.dumps({"command": "title"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Usage", response.json()["error"])
