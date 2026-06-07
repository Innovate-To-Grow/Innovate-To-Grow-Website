from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    SystemIntelligenceConfig,
)


class CleanupCommandTests(TestCase):
    def setUp(self):
        self.config = SystemIntelligenceConfig.objects.create(
            name="Cfg", is_active=True, public_assistant_log_retention_days=30
        )

    def _convo(self, last_activity_at):
        convo = AssistantConversationLog.objects.create(
            source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            last_activity_at=last_activity_at,
        )
        AssistantMessageLog.objects.create(conversation=convo, prompt="hi", status=AssistantMessageLog.STATUS_OK)
        return convo

    def test_deletes_old_keeps_recent(self):
        old = self._convo(timezone.now() - timedelta(days=31))
        recent = self._convo(timezone.now() - timedelta(days=1))

        out = StringIO()
        call_command("system_intelligence_cleanup", stdout=out)

        self.assertFalse(AssistantConversationLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AssistantConversationLog.objects.filter(pk=recent.pk).exists())
        # Cascade removed the old conversation's message too.
        self.assertEqual(AssistantMessageLog.objects.count(), 1)
        self.assertIn("Removed", out.getvalue())

    def test_retention_zero_is_a_noop(self):
        self.config.public_assistant_log_retention_days = 0
        self.config.save()
        self._convo(timezone.now() - timedelta(days=365))

        out = StringIO()
        call_command("system_intelligence_cleanup", stdout=out)

        self.assertEqual(AssistantConversationLog.objects.count(), 1)
        self.assertIn("keep forever", out.getvalue())
