import json
import uuid

from django.urls import reverse

from apps.system_intelligence.models import ChatConversation, ChatMessage
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class ConversationsFragmentTests(SystemIntelligenceAdminBase):
    def test_lists_current_user_conversations(self):
        self.conversation.title = "My Chat"
        self.conversation.save(update_fields=["title", "updated_at"])
        response = self.client.get(reverse("admin:system_intelligence_conversations"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["conversations"]), 1)
        entry = body["conversations"][0]
        self.assertEqual(entry["id"], str(self.conversation.id))
        self.assertEqual(entry["title"], "My Chat")
        self.assertEqual(entry["mode"], self.conversation.mode)
        self.assertIn(",", entry["updated_at"])  # formatted "%b %d, %H:%M"


class NewConversationViewTests(SystemIntelligenceAdminBase):
    def test_requires_post(self):
        response = self.client.get(reverse("admin:system_intelligence_new"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "POST required")

    def test_creates_conversation_for_user(self):
        before = ChatConversation.objects.filter(created_by=self.admin_user).count()
        response = self.client.post(reverse("admin:system_intelligence_new"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        new_convo = ChatConversation.objects.get(id=body["id"])
        self.assertEqual(new_convo.created_by, self.admin_user)
        self.assertEqual(body["title"], new_convo.title)
        self.assertEqual(body["mode"], new_convo.mode)
        self.assertEqual(ChatConversation.objects.filter(created_by=self.admin_user).count(), before + 1)


class ChatDeleteViewTests(SystemIntelligenceAdminBase):
    def test_requires_post(self):
        response = self.client.get(reverse("admin:system_intelligence_delete", args=[self.conversation.id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "POST required")

    def test_deletes_owned_conversation(self):
        response = self.client.post(reverse("admin:system_intelligence_delete", args=[self.conversation.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertFalse(ChatConversation.objects.filter(id=self.conversation.id).exists())

    def test_returns_404_for_unknown_conversation(self):
        response = self.client.post(reverse("admin:system_intelligence_delete", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Conversation not found")


class ChatRenameViewTests(SystemIntelligenceAdminBase):
    def _rename(self, body, conversation_id=None):
        return self.client.post(
            reverse("admin:system_intelligence_rename", args=[conversation_id or self.conversation.id]),
            data=body,
            content_type="application/json",
        )

    def test_requires_post(self):
        response = self.client.get(reverse("admin:system_intelligence_rename", args=[self.conversation.id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "POST required")

    def test_returns_404_for_unknown_conversation(self):
        response = self._rename(json.dumps({"title": "X"}), conversation_id=uuid.uuid4())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Conversation not found")

    def test_rejects_invalid_json_body(self):
        response = self._rename("not-json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON body")

    def test_rejects_empty_title(self):
        response = self._rename(json.dumps({"title": "   "}))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Title cannot be empty")

    def test_renames_and_disables_auto_title(self):
        long_title = "x" * 250
        response = self._rename(json.dumps({"title": long_title}))
        self.assertEqual(response.status_code, 200)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "x" * 200)
        self.assertFalse(self.conversation.auto_title)
        self.assertEqual(response.json()["title"], "x" * 200)


class ChatViewMessagesTests(SystemIntelligenceAdminBase):
    def test_returns_404_for_unknown_conversation(self):
        response = self.client.get(reverse("admin:system_intelligence_detail", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Conversation not found")

    def test_serializes_messages_with_metadata(self):
        ChatMessage.objects.create(
            conversation=self.conversation,
            role="assistant",
            content="hi",
            model_id="model-x",
            tool_calls=[{"name": "t"}],
            token_usage={"totalTokens": 3},
            context_usage={"preparedMessageCount": 1},
        )
        response = self.client.get(reverse("admin:system_intelligence_detail", args=[self.conversation.id]))
        self.assertEqual(response.status_code, 200)
        message = response.json()["messages"][-1]
        self.assertEqual(message["content"], "hi")
        self.assertEqual(message["model_id"], "model-x")
        self.assertEqual(message["tool_calls"], [{"name": "t"}])
        self.assertEqual(message["token_usage"], {"totalTokens": 3})
        self.assertEqual(message["context_usage"], {"preparedMessageCount": 1})
