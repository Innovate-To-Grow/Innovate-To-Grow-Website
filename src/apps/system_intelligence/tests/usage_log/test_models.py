from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog


def make_conversation(**overrides):
    defaults = {
        "source": AssistantConversationLog.SOURCE_PUBLIC_CHAT,
        "last_activity_at": timezone.now(),
    }
    defaults.update(overrides)
    return AssistantConversationLog.objects.create(**defaults)


class AssistantConversationLogModelTests(TestCase):
    def test_unique_constraint_blocks_duplicate_source_session(self):
        session = "11111111-1111-1111-1111-111111111111"
        make_conversation(session_id=session)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_conversation(session_id=session)

    def test_null_session_id_allows_many_rows(self):
        # The partial unique constraint only applies when session_id IS NOT NULL.
        make_conversation(session_id=None)
        make_conversation(session_id=None)
        self.assertEqual(AssistantConversationLog.objects.filter(session_id__isnull=True).count(), 2)

    def test_same_session_different_source_is_allowed(self):
        session = "22222222-2222-2222-2222-222222222222"
        make_conversation(source=AssistantConversationLog.SOURCE_PUBLIC_CHAT, session_id=session)
        make_conversation(source=AssistantConversationLog.SOURCE_AI_SEARCH, session_id=session)
        self.assertEqual(AssistantConversationLog.objects.filter(session_id=session).count(), 2)

    def test_str(self):
        convo = make_conversation(message_count=3)
        self.assertEqual(str(convo), "Public Chat conversation (3 turns)")

    def test_ordering_newest_activity_first(self):
        older = make_conversation(last_activity_at=timezone.now() - timezone.timedelta(hours=2))
        newer = make_conversation(last_activity_at=timezone.now())
        self.assertEqual(list(AssistantConversationLog.objects.all()), [newer, older])


class AssistantMessageLogModelTests(TestCase):
    def setUp(self):
        self.conversation = make_conversation()

    def test_cascade_delete_removes_messages(self):
        AssistantMessageLog.objects.create(
            conversation=self.conversation,
            prompt="hi",
            status=AssistantMessageLog.STATUS_OK,
        )
        self.conversation.delete()
        self.assertEqual(AssistantMessageLog.objects.count(), 0)

    def test_str_short_prompt(self):
        message = AssistantMessageLog.objects.create(
            conversation=self.conversation,
            prompt="short",
            status=AssistantMessageLog.STATUS_OK,
        )
        self.assertEqual(str(message), "[ok] short")

    def test_str_truncates_long_prompt(self):
        message = AssistantMessageLog.objects.create(
            conversation=self.conversation,
            prompt="x" * 100,
            status=AssistantMessageLog.STATUS_ERROR,
        )
        self.assertTrue(str(message).endswith("..."))
        self.assertTrue(str(message).startswith("[error] "))

    def test_ordering_oldest_first(self):
        first = AssistantMessageLog.objects.create(
            conversation=self.conversation, prompt="first", status=AssistantMessageLog.STATUS_OK
        )
        second = AssistantMessageLog.objects.create(
            conversation=self.conversation, prompt="second", status=AssistantMessageLog.STATUS_OK
        )
        self.assertEqual(list(self.conversation.messages.all()), [first, second])
