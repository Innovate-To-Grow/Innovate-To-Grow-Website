import json
from unittest.mock import patch

from django.urls import reverse

from system_intelligence.models import ChatMessage, SystemIntelligenceActionRequest
from system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminSendTests(SystemIntelligenceAdminBase):
    def test_send_stream_preserves_sse_protocol_and_persists_assistant_metadata(self):
        stream_events = [
            {"type": "text", "chunk": "Hello"},
            {
                "type": "tool_call",
                "name": "search_members",
                "input": {"name": "Ada"},
                "result_preview": "Showing 1 of 1 result.",
            },
            {"type": "usage", "inputTokens": 2, "outputTokens": 3, "totalTokens": 5},
        ]
        with patch(
            "system_intelligence.admin.invoke_system_intelligence_stream", return_value=iter(stream_events)
        ) as stream:
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "Find Ada"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn('event: context\ndata: {"contextWindow": 200000', body)
        self.assertIn('event: text\ndata: {"chunk": "Hello"}', body)
        self.assertLess(body.index("event: context"), body.index("event: text"))
        self.assertIn('event: tool_call\ndata: {"type": "tool_call"', body)
        self.assertIn('event: usage\ndata: {"inputTokens": 2, "outputTokens": 3, "totalTokens": 5}', body)
        self.assertIn('event: done\ndata: {"id":', body)
        self.assertEqual(stream.call_args.args[0], [{"role": "user", "content": "Find Ada"}])
        self.assertEqual(stream.call_args.kwargs["chat_config"], self.chat_config)
        self.assertEqual(stream.call_args.kwargs["aws_config"], self.aws_config)
        messages = list(ChatMessage.objects.filter(conversation=self.conversation).order_by("created_at"))
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[1].content, "Hello")
        self.assertEqual(messages[1].token_usage, {"inputTokens": 2, "outputTokens": 3, "totalTokens": 5})
        self.assertEqual(messages[1].context_usage["preparedMessageCount"], 1)
        detail = self.client.get(reverse("admin:system_intelligence_detail", args=[self.conversation.id]))
        self.assertEqual(detail.json()["messages"][-1]["context_usage"]["preparedMessageCount"], 1)

    def test_send_stream_emits_action_request_and_links_it_to_assistant_message(self):
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk="123",
            target_repr="Feed",
            title="Update feed",
            summary="Needs review.",
            diff=[{"field": "name", "before": "Old", "after": "New"}],
        )
        event = {
            "type": "action_request",
            "id": str(action.id),
            "status": "pending",
            "action_type": "db_update",
            "title": "Update feed",
            "summary": "Needs review.",
            "target": {"app_label": "cms", "model": "NewsFeedSource", "pk": "123", "repr": "Feed"},
            "diff": [{"field": "name", "before": "Old", "after": "New"}],
            "preview_url": "",
            "created_at": "2026-04-25T00:00:00",
        }
        with patch(
            "system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "text", "chunk": "I prepared a change."}, event]),
        ):
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "Change it"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()
        self.assertIn("event: action_request", body)
        action.refresh_from_db()
        self.assertEqual(action.assistant_message.content, "I prepared a change.")
        detail = self.client.get(reverse("admin:system_intelligence_detail", args=[self.conversation.id]))
        self.assertEqual(detail.json()["messages"][-1]["action_requests"][0]["id"], str(action.id))

    def test_send_rejects_messages_above_length_cap(self):
        from system_intelligence.admin.stream import USER_MESSAGE_MAX_CHARS

        oversized = "x" * (USER_MESSAGE_MAX_CHARS + 1)
        response = self.client.post(
            reverse("admin:system_intelligence_send", args=[self.conversation.id]),
            data=json.dumps({"message": oversized}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("characters", response.json()["error"])
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation, role="user").exists())

    def test_send_does_not_overwrite_user_renamed_title_named_new_chat(self):
        from system_intelligence.models import ChatConversation

        ChatConversation.objects.filter(pk=self.conversation.pk).update(title="New Chat", auto_title=False)
        with patch(
            "system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "text", "chunk": "Hi"}]),
        ):
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "First message that would otherwise become the title."}),
                content_type="application/json",
            )
            b"".join(response.streaming_content)

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "New Chat")
        self.assertFalse(self.conversation.auto_title)

    def test_send_stream_sanitizes_bedrock_dns_error(self):
        raw_error = "litellm.ServiceUnavailableError: BedrockException - Cannot connect to host bedrock-runtime.us-west-2.amazonaws.com:443 ssl:<ssl.SSLContext object> [Could not contact DNS servers]"
        with patch(
            "system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "error", "error": raw_error}]),
        ):
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "hello"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()
        self.assertIn("Unable to reach AWS Bedrock Runtime in us-west-2", body)
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation, role="assistant").exists())
