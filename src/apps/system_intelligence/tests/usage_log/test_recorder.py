from unittest.mock import patch

from django.test import TestCase

from apps.event.tests.helpers import make_member
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.usage_log import log_assistant_turn

SESSION = "33333333-3333-3333-3333-333333333333"
SOURCE = AssistantConversationLog.SOURCE_PUBLIC_CHAT


class RecorderTests(TestCase):
    def setUp(self):
        self.config = SystemIntelligenceConfig.objects.create(
            name="Cfg", is_active=True, public_assistant_log_enabled=True
        )

    def _log(self, **overrides):
        defaults = {
            "source": SOURCE,
            "session_id": SESSION,
            "ip_hash": "abc",
            "prompt": "What is I2G?",
            "reply": "It connects students with industry.",
            "status": AssistantMessageLog.STATUS_OK,
            "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "token_usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
            "latency_ms": 42,
            "config": self.config,
        }
        defaults.update(overrides)
        log_assistant_turn(**defaults)

    def test_creates_conversation_and_message(self):
        self._log()
        convo = AssistantConversationLog.objects.get()
        self.assertEqual(convo.source, SOURCE)
        self.assertEqual(str(convo.session_id), SESSION)
        self.assertEqual(convo.message_count, 1)
        self.assertEqual(convo.total_tokens, 15)
        self.assertEqual(convo.ip_hash, "abc")
        message = convo.messages.get()
        self.assertEqual(message.prompt, "What is I2G?")
        self.assertEqual(message.status, AssistantMessageLog.STATUS_OK)
        self.assertEqual(message.latency_ms, 42)
        self.assertEqual(message.token_usage["totalTokens"], 15)

    def test_same_session_reuses_conversation_and_increments(self):
        self._log()
        self._log(token_usage={"totalTokens": 20})
        self.assertEqual(AssistantConversationLog.objects.count(), 1)
        convo = AssistantConversationLog.objects.get()
        self.assertEqual(convo.message_count, 2)
        self.assertEqual(convo.total_tokens, 35)
        self.assertEqual(convo.messages.count(), 2)

    def test_garbage_session_id_creates_standalone_conversations(self):
        self._log(session_id="not-a-uuid")
        self._log(session_id="also-garbage")
        self.assertEqual(AssistantConversationLog.objects.count(), 2)
        self.assertTrue(all(c.session_id is None for c in AssistantConversationLog.objects.all()))

    def test_blank_session_id_creates_standalone_conversations(self):
        self._log(session_id="")
        self._log(session_id=None)
        self.assertEqual(AssistantConversationLog.objects.count(), 2)
        self.assertEqual(AssistantConversationLog.objects.filter(session_id__isnull=True).count(), 2)

    def test_disabled_logging_writes_nothing(self):
        self.config.public_assistant_log_enabled = False
        self.config.save()
        self._log()
        self.assertEqual(AssistantConversationLog.objects.count(), 0)
        self.assertEqual(AssistantMessageLog.objects.count(), 0)

    def test_loads_config_when_not_passed(self):
        # No config kwarg -> recorder loads the active config itself.
        log_assistant_turn(
            source=SOURCE,
            session_id=None,
            ip_hash="x",
            prompt="hi",
            status=AssistantMessageLog.STATUS_OK,
        )
        self.assertEqual(AssistantConversationLog.objects.count(), 1)

    def test_records_user_and_backfills_on_reuse(self):
        member = make_member(email="convo@example.com")
        # First turn has no user; second supplies one -> conversation backfills it.
        self._log(user=None)
        self._log(user=member)
        convo = AssistantConversationLog.objects.get()
        self.assertEqual(convo.user_id, member.id)

    def test_failure_is_isolated_and_never_raises(self):
        # Force an exception deep inside the recorder; it must swallow it.
        with patch(
            "apps.system_intelligence.services.usage_log.recorder.AssistantMessageLog.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise.
            self._log()
        # The atomic block rolled back, so no partial conversation remains.
        self.assertEqual(AssistantConversationLog.objects.count(), 0)

    def test_failure_logging_itself_failing_never_raises(self):
        # Even a broken logging handler must stay silent: the never-raise
        # contract holds when logger.exception itself blows up.
        with (
            patch(
                "apps.system_intelligence.services.usage_log.recorder.AssistantMessageLog.objects.create",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "apps.system_intelligence.services.usage_log.recorder.logger.exception",
                side_effect=RuntimeError("logging broken"),
            ),
        ):
            # Must not raise.
            self._log()
        self.assertEqual(AssistantConversationLog.objects.count(), 0)

    def test_counter_increments_apply_atomically_in_the_database(self):
        # Simulate a concurrent turn racing this one: get_or_create returns a
        # STALE instance while the row was already bumped in the database. The
        # F() expressions must add on top of the DB values, not the stale read
        # (read-modify-write would write 2/30 here and lose the update).
        self._log()
        stale = AssistantConversationLog.objects.get()
        AssistantConversationLog.objects.filter(pk=stale.pk).update(message_count=5, total_tokens=50)
        with patch(
            "apps.system_intelligence.services.usage_log.recorder.AssistantConversationLog.objects.get_or_create",
            return_value=(stale, False),
        ):
            self._log()
        stale.refresh_from_db()
        self.assertEqual(stale.message_count, 6)
        self.assertEqual(stale.total_tokens, 65)
