from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceExport


class ExportFileCleanupSignalTests(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.conversation = ChatConversation.objects.create(created_by=self.user)

    def _export(self, with_file=True):
        export = SystemIntelligenceExport(
            conversation=self.conversation, created_by=self.user, title="T", filename="t.xlsx"
        )
        if with_file:
            export.file.save("t.xlsx", ContentFile(b"xlsx"), save=False)
        export.save()
        return export

    def test_delete_removes_file_after_commit(self):
        export = self._export()
        storage, name = export.file.storage, export.file.name
        self.assertTrue(storage.exists(name))

        with self.captureOnCommitCallbacks(execute=True):
            export.delete()

        self.assertFalse(storage.exists(name))

    def test_conversation_cascade_removes_file(self):
        export = self._export()
        storage, name = export.file.storage, export.file.name

        with self.captureOnCommitCallbacks(execute=True):
            self.conversation.delete()

        self.assertFalse(storage.exists(name))

    def test_missing_file_is_a_noop(self):
        export = self._export(with_file=False)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            export.delete()
        self.assertEqual(callbacks, [])

    def test_storage_failure_is_logged_not_raised(self):
        export = self._export()
        with (
            patch("django.core.files.storage.FileSystemStorage.delete", side_effect=OSError("disk")),
            self.assertLogs("apps.system_intelligence.signals", level="WARNING") as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            export.delete()
        self.assertIn("Could not delete export file", logs.output[0])
