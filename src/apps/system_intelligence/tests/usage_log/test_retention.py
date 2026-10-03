"""Retention of audited assistant conversations: batched, stoppable, and never run on a default nobody chose."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.usage_log import (
    conversation_log_retention_days,
    purge_expired_conversation_logs,
)


class ConversationLogRetentionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.config = SystemIntelligenceConfig.objects.create(
            name="Cfg", is_active=True, public_assistant_log_retention_days=30
        )

    def conversation(self, *, days_old, messages=1):
        conversation = AssistantConversationLog.objects.create(
            source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            last_activity_at=self.now - timedelta(days=days_old),
        )
        for _ in range(messages):
            AssistantMessageLog.objects.create(
                conversation=conversation, prompt="hi", status=AssistantMessageLog.STATUS_OK
            )
        return conversation

    def test_only_conversations_past_the_retention_window_are_deleted_with_their_messages(self):
        old = self.conversation(days_old=31, messages=3)
        recent = self.conversation(days_old=29, messages=2)

        deleted = purge_expired_conversation_logs(now=self.now)

        # One conversation and its three messages.
        self.assertEqual(deleted, 4)
        self.assertFalse(AssistantConversationLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AssistantConversationLog.objects.filter(pk=recent.pk).exists())
        self.assertEqual(AssistantMessageLog.objects.count(), 2)

    def test_a_conversation_exactly_at_the_cutoff_is_kept(self):
        self.conversation(days_old=30)

        self.assertEqual(purge_expired_conversation_logs(now=self.now), 0)
        self.assertEqual(AssistantConversationLog.objects.count(), 1)

    def test_zero_retention_keeps_everything(self):
        self.config.public_assistant_log_retention_days = 0
        self.config.save()
        self.conversation(days_old=3650)

        self.assertEqual(conversation_log_retention_days(), 0)
        self.assertEqual(purge_expired_conversation_logs(now=self.now), 0)
        self.assertEqual(AssistantConversationLog.objects.count(), 1)

    def test_a_backlog_is_deleted_oldest_first_in_bounded_batches(self):
        for days_old in range(40, 50):
            self.conversation(days_old=days_old)
        self.conversation(days_old=1)

        seen = []

        def should_stop():
            seen.append(AssistantConversationLog.objects.count())
            return False

        deleted = purge_expired_conversation_logs(batch_size=3, should_stop=should_stop, now=self.now)

        # 10 expired conversations with one message each, in batches of 3, 3, 3 and 1.
        self.assertEqual(deleted, 20)
        self.assertEqual(seen, [11, 8, 5, 2])
        self.assertEqual(AssistantConversationLog.objects.count(), 1)

    def test_a_stop_request_ends_the_run_after_the_batch_in_flight(self):
        for days_old in range(40, 50):
            self.conversation(days_old=days_old)
        checks = iter([False, True])

        deleted = purge_expired_conversation_logs(batch_size=4, should_stop=lambda: next(checks), now=self.now)

        # One batch of four conversations (and their messages) was committed; the rest waits for the next run.
        self.assertEqual(deleted, 8)
        self.assertEqual(AssistantConversationLog.objects.count(), 6)
        oldest_left = AssistantConversationLog.objects.order_by("last_activity_at").first()
        self.assertEqual(oldest_left.last_activity_at, self.now - timedelta(days=45))

    def test_without_an_active_configuration_nothing_is_deleted(self):
        """``load()`` then returns model defaults (90 days); a destructive cleanup must not act on those."""
        self.config.public_assistant_log_retention_days = 0
        self.config.is_active = False
        self.config.save()
        self.conversation(days_old=3650)

        self.assertEqual(conversation_log_retention_days(), 0)
        self.assertEqual(purge_expired_conversation_logs(now=self.now), 0)
        self.assertEqual(AssistantConversationLog.objects.count(), 1)

    def test_with_no_configuration_row_at_all_nothing_is_deleted(self):
        SystemIntelligenceConfig.objects.all().delete()
        self.conversation(days_old=3650)

        self.assertEqual(purge_expired_conversation_logs(now=self.now), 0)
        self.assertEqual(AssistantConversationLog.objects.count(), 1)

    def test_a_retention_longer_than_the_calendar_keeps_everything(self):
        self.config.public_assistant_log_retention_days = 2_000_000_000
        self.config.save()
        self.conversation(days_old=3650)

        self.assertEqual(purge_expired_conversation_logs(now=self.now), 0)
        self.assertEqual(AssistantConversationLog.objects.count(), 1)

    def test_the_background_worker_does_not_schedule_this_cleanup(self):
        """Deleting audit records is the operator's call: only the management command runs it."""
        from apps.core.management.commands import run_background_worker

        names = [name for name, _task in run_background_worker.MAINTENANCE_TASKS]

        self.assertFalse([name for name in names if "ssistant conversation" in name])
        self.assertFalse(hasattr(run_background_worker, "purge_expired_conversation_logs"))
