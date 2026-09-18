from datetime import timedelta
from io import StringIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    ChatConversation,
    SystemIntelligenceConfig,
    SystemIntelligenceExport,
)


class CleanupCommandTests(TestCase):
    def setUp(self):
        self.config = SystemIntelligenceConfig.objects.create(
            name="Cfg", is_active=True, public_assistant_log_retention_days=30, export_retention_days=30
        )

    def _export(self, created_at):
        user = make_superuser(email=f"{created_at.timestamp()}@example.com")
        conversation = ChatConversation.objects.create(created_by=user)
        export = SystemIntelligenceExport(conversation=conversation, created_by=user, title="T", filename="t.xlsx")
        export.file.save("t.xlsx", ContentFile(b"xlsx"), save=False)
        export.save()
        # created_at is auto_now_add; backdate it after the insert.
        SystemIntelligenceExport.objects.filter(pk=export.pk).update(created_at=created_at)
        return export

    def test_deletes_old_exports_and_their_files_keeps_recent(self):
        old = self._export(timezone.now() - timedelta(days=31))
        recent = self._export(timezone.now() - timedelta(days=1))
        storage, old_name = old.file.storage, old.file.name

        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("system_intelligence_cleanup", stdout=out)

        self.assertFalse(SystemIntelligenceExport.objects.filter(pk=old.pk).exists())
        self.assertTrue(SystemIntelligenceExport.objects.filter(pk=recent.pk).exists())
        self.assertFalse(storage.exists(old_name))
        self.assertTrue(storage.exists(recent.file.name))
        self.assertIn("Removed 1 export(s)", out.getvalue())

    def test_export_retention_zero_is_a_noop(self):
        self.config.export_retention_days = 0
        self.config.save()
        self._export(timezone.now() - timedelta(days=365))

        out = StringIO()
        call_command("system_intelligence_cleanup", stdout=out)

        self.assertEqual(SystemIntelligenceExport.objects.count(), 1)
        self.assertIn("no exports deleted", out.getvalue())

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
