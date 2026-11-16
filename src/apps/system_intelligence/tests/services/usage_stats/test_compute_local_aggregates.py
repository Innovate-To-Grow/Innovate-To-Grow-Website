from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    ChatConversation,
    ChatMessage,
)
from apps.system_intelligence.services.usage_stats import (
    compute_local_aggregates,
)


class ComputeLocalAggregatesTest(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.convo = AssistantConversationLog.objects.create(
            source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            session_id="33333333-3333-3333-3333-333333333333",
            message_count=2,
            total_tokens=150,
            last_activity_at=self.now,
        )
        AssistantMessageLog.objects.create(
            conversation=self.convo,
            prompt="What is I2G?",
            status=AssistantMessageLog.STATUS_OK,
            token_usage={
                "inputTokens": 100,
                "outputTokens": 50,
                "totalTokens": 150,
                "cacheReadInputTokens": 60,
                "cacheWriteInputTokens": 20,
            },
        )
        AssistantMessageLog.objects.create(
            conversation=self.convo, prompt="What is I2G?", status=AssistantMessageLog.STATUS_OK
        )
        AssistantConversationLog.objects.create(
            source=AssistantConversationLog.SOURCE_AI_SEARCH,
            message_count=1,
            total_tokens=40,
            last_activity_at=self.now,
        )

        # Admin chat tokens live in ChatMessage.token_usage JSON.
        from apps.event.tests.helpers import make_superuser

        admin_user = make_superuser(email="aggadmin@example.com")
        chat = ChatConversation.objects.create(created_by=admin_user)
        ChatMessage.objects.create(
            conversation=chat,
            role="assistant",
            content="ok",
            model_id="anthropic.claude",
            token_usage={
                "inputTokens": 30,
                "outputTokens": 40,
                "totalTokens": 70,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
            },
        )
        ChatMessage.objects.create(conversation=chat, role="assistant", content="ok", token_usage={"totalTokens": None})
        ChatMessage.objects.create(conversation=chat, role="assistant", content="ok", token_usage={})

    def test_counts(self):
        result = compute_local_aggregates()
        counts = result["counts"]
        self.assertEqual(counts["conversations_today"], 2)
        self.assertEqual(counts["conversations_30d"], 2)
        self.assertEqual(counts["messages_30d"], 3)  # 2 + 1 message_count
        self.assertEqual(counts["messages_7d"], 3)

    def test_rolling_24h_uses_local_message_logs_and_admin_chat(self):
        result = compute_local_aggregates()
        rolling = result["rolling_24h"]
        self.assertEqual(rolling["input_tokens"], 130)
        self.assertEqual(rolling["output_tokens"], 90)
        # Two public/search AssistantMessageLog rows + one admin assistant model call.
        self.assertEqual(rolling["invocations"], 3)
        self.assertEqual(rolling["cache_read_tokens"], 70)
        self.assertEqual(rolling["cache_write_tokens"], 25)
        self.assertEqual(rolling["cache_total_tokens"], 95)
        self.assertEqual(rolling["cache_hit_rate"], 73.7)

    def test_tokens_by_source_includes_admin_chat_summed_in_python(self):
        result = compute_local_aggregates()
        by_source = {row["source"]: row["total_tokens"] for row in result["tokens_by_source"]}
        self.assertEqual(by_source[AssistantConversationLog.SOURCE_PUBLIC_CHAT], 150)
        self.assertEqual(by_source[AssistantConversationLog.SOURCE_AI_SEARCH], 40)
        # 70 + (None -> 0) + ({} -> 0) == 70.
        self.assertEqual(by_source["admin_chat"], 70)
        labels = {row["source"]: row["label"] for row in result["tokens_by_source"]}
        self.assertEqual(labels["admin_chat"], "Admin Chat")

    def test_recent_conversations_shape(self):
        result = compute_local_aggregates()
        recent = result["recent"]
        self.assertEqual(len(recent), 2)
        first = recent[0]
        self.assertIn("id", first)
        self.assertIn(first["source"], {"public_chat", "ai_search"})
        self.assertTrue(first["last_activity"])  # ISO string
        # Session short or em dash.
        self.assertTrue(first["session"])

    def test_top_prompts(self):
        result = compute_local_aggregates()
        prompts = result["top_prompts"]
        self.assertEqual(prompts[0]["prompt"], "What is I2G?")
        self.assertEqual(prompts[0]["count"], 2)

    def test_json_serializable(self):
        import json

        result = compute_local_aggregates()
        # Must not raise -- everything is primitives/ISO strings.
        json.dumps(result)

    def test_db_failure_degrades_to_zeroed_shape(self):
        # The dashboard must never 500 on local stats: any ORM failure yields
        # the same shape with everything zeroed/empty.
        with patch(
            "apps.system_intelligence.services.usage_stats.aggregates.AssistantConversationLog.objects.order_by",
            side_effect=RuntimeError("db down"),
        ):
            result = compute_local_aggregates()
        self.assertEqual(result["counts"]["conversations_30d"], 0)
        self.assertEqual(result["counts"]["messages_today"], 0)
        self.assertEqual(
            result["rolling_24h"],
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "invocations": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cache_total_tokens": 0,
                "cache_hit_rate": 0,
            },
        )
        self.assertEqual(result["recent"], [])
        self.assertEqual(result["top_prompts"], [])
        self.assertEqual(len(result["tokens_by_source"]), 3)
        self.assertTrue(all(row["total_tokens"] == 0 for row in result["tokens_by_source"]))
