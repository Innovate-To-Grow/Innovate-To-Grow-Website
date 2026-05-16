from unittest.mock import patch

from django.test import TestCase

from core.models import AWSCredentialConfig
from event.tests.helpers import make_superuser
from system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
)
from system_intelligence.services.adk.context_manager import prepare_conversation_context


class SystemIntelligenceContextManagerTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            system_prompt="Use tools.",
        )
        self.conversation = ChatConversation.objects.create(created_by=self.admin_user)

    def add_message(self, role, content):
        return ChatMessage.objects.create(conversation=self.conversation, role=role, content=content)

    def prepare(self):
        messages = list(self.conversation.messages.order_by("created_at"))
        return prepare_conversation_context(
            self.conversation,
            messages,
            chat_config=self.chat_config,
            aws_config=self.aws_config,
            model_id=self.aws_config.default_model_id,
            user_id=str(self.admin_user.pk),
        )

    def test_low_context_uses_full_history_without_summary(self):
        self.add_message("user", "Earlier question")
        self.add_message("assistant", "Earlier answer")
        self.add_message("user", "Current question")

        prepared = self.prepare()

        self.assertFalse(prepared.error)
        self.assertFalse(prepared.usage["compacted"])
        self.assertEqual(
            [message["content"] for message in prepared.messages],
            ["Earlier question", "Earlier answer", "Current question"],
        )
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.context_summary, "")

    def test_compaction_updates_persistent_summary_and_omits_old_raw_messages(self):
        for index in range(30):
            self.add_message("user" if index % 2 == 0 else "assistant", f"Older message {index} " + ("x" * 80))
        self.add_message("user", "Current question")

        with (
            patch(
                "system_intelligence.services.adk.context_manager.prepare.estimate_context_window",
                return_value=1000,
            ),
            patch(
                "system_intelligence.services.adk.context_manager.summary.summarize_context",
                return_value="Useful summary",
            ),
        ):
            prepared = self.prepare()

        self.assertFalse(prepared.error)
        self.assertTrue(prepared.usage["compacted"])
        self.assertTrue(prepared.usage["summaryUsed"])
        self.assertTrue(prepared.usage["summaryUpdated"])
        self.assertEqual(prepared.usage["summarizedMessages"], 6)
        self.assertIn("Useful summary", prepared.messages[0]["content"])
        self.assertNotIn("Older message 0", "\n".join(message["content"] for message in prepared.messages[1:]))
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.context_summary, "Useful summary")
        self.assertTrue(self.conversation.context_summary_through_message_id)

    def test_hard_limit_trims_recent_messages_but_keeps_minimum_recent_turns(self):
        for index in range(32):
            self.add_message("user" if index % 2 == 0 else "assistant", f"Recent-heavy {index} " + ("x" * 100))
        self.add_message("user", "Current question")

        with (
            patch(
                "system_intelligence.services.adk.context_manager.prepare.estimate_context_window",
                return_value=1000,
            ),
            patch(
                "system_intelligence.services.adk.context_manager.summary.summarize_context",
                return_value="Useful summary",
            ),
        ):
            prepared = self.prepare()

        self.assertFalse(prepared.error)
        self.assertGreater(prepared.usage["trimmedMessages"], 0)
        self.assertGreaterEqual(prepared.usage["retainedMessages"], 9)
        self.assertLessEqual(prepared.usage["preparedTokens"], prepared.usage["hardLimit"])

    def test_pending_action_context_is_included(self):
        self.add_message("user", "Current question")
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            target_pk="123",
            target_repr="Page",
            title="Update CMS page",
            summary="Needs approval.",
            diff=[],
        )

        prepared = self.prepare()

        self.assertIn(str(action.id), prepared.messages[0]["content"])
        self.assertIn("not applied until an admin approves", prepared.messages[0]["content"])

    def test_summary_failure_uses_fallback_without_creating_assistant_message(self):
        for index in range(30):
            self.add_message("user" if index % 2 == 0 else "assistant", f"Older message {index} " + ("x" * 80))
        self.add_message("user", "Current question")
        initial_message_count = ChatMessage.objects.filter(conversation=self.conversation).count()

        with (
            patch(
                "system_intelligence.services.adk.context_manager.prepare.estimate_context_window",
                return_value=1000,
            ),
            patch(
                "system_intelligence.services.adk.context_manager.summary.summarize_context",
                side_effect=RuntimeError("down"),
            ),
            patch("system_intelligence.services.adk.context_manager.summary.logger.exception"),
        ):
            prepared = self.prepare()

        self.assertFalse(prepared.error)
        self.assertTrue(prepared.usage["summaryFailed"])
        self.conversation.refresh_from_db()
        self.assertIn("Older message", self.conversation.context_summary)
        self.assertEqual(ChatMessage.objects.filter(conversation=self.conversation).count(), initial_message_count)
