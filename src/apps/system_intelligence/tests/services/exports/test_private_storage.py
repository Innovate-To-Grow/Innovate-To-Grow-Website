from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import TransientJobError
from apps.event.tests.helpers import make_admin
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceExport
from apps.system_intelligence.services.tools.exports.cleanup import (
    CLEANUP_JOB,
    delete_export_job,
    iter_private_orphans,
)
from apps.system_intelligence.services.tools.exports.migration import migrate_export


class PrivateExportStorageTests(TestCase):
    def setUp(self):
        self.legacy = InMemoryStorage()
        self.private = InMemoryStorage()
        self.user = make_admin()
        self.chat = ChatConversation.objects.create(created_by=self.user)
        export = SystemIntelligenceExport(
            conversation=self.chat, created_by=self.user, filename="members.xlsx", model_label="authn.Member"
        )
        self.key = f"system_intelligence_exports/{export.pk}/{export.filename}"
        self.legacy.save(self.key, ContentFile(b"spreadsheet"))
        export.file = self.key
        export.save()
        self.export = export
        self.enterContext(
            patch("apps.system_intelligence.services.tools.exports.migration.default_storage", self.legacy)
        )
        for module in ("cleanup", "migration"):
            self.enterContext(
                patch(
                    f"apps.system_intelligence.services.tools.exports.{module}.private_export_storage",
                    return_value=self.private,
                )
            )
        self.enterContext(patch.object(SystemIntelligenceExport._meta.get_field("file"), "storage", self.legacy))
        self.enterContext(
            patch.object(SystemIntelligenceExport._meta.get_field("private_file"), "storage", self.private)
        )
        self.client.force_login(self.user)
        self.url = reverse("admin:system_intelligence_export_download", args=[export.pk])

    def test_migration_is_resumable_preserves_url_and_retires_verified_copy(self):
        self.assertEqual(b"".join(self.client.get(self.url).streaming_content), b"spreadsheet")
        self.assertEqual(migrate_export(self.export.pk), "migrated")
        self.assertEqual(migrate_export(self.export.pk), "unchanged")
        self.assertEqual(migrate_export(self.export.pk, retire=True), "retired")
        self.assertFalse(self.legacy.exists(self.key))
        response = self.client.get(self.url)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(b"".join(response.streaming_content), b"spreadsheet")
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_retirement_needs_matching_private_file(self):
        self.assertEqual(migrate_export(self.export.pk, retire=True), "not_migrated")
        self.private.save(self.key, ContentFile(b"different"))
        self.assertEqual(migrate_export(self.export.pk), "checksum_mismatch")
        self.assertTrue(self.legacy.exists(self.key))

    def test_missing_private_object_returns_410_without_falling_back(self):
        self.assertEqual(migrate_export(self.export.pk), "migrated")
        self.private.delete(self.key)
        self.assertEqual(self.client.get(self.url).status_code, 410)
        self.assertTrue(self.legacy.exists(self.key))

    def test_cascade_queues_after_commit_and_job_can_retry(self):
        self.assertEqual(migrate_export(self.export.pk), "migrated")
        with self.assertRaisesMessage(RuntimeError, "rollback"), transaction.atomic():
            ChatConversation.objects.filter(pk=self.chat.pk).delete()
            raise RuntimeError("rollback")
        self.assertFalse(BackgroundJob.objects.filter(kind=CLEANUP_JOB).exists())
        self.assertTrue(self.private.exists(self.key))
        self.chat.delete()
        job = BackgroundJob.objects.get(kind=CLEANUP_JOB)
        self.assertTrue(self.private.exists(self.key))
        with (
            patch.object(self.private, "delete", side_effect=OSError("temporary error")),
            self.assertRaises(TransientJobError),
        ):
            delete_export_job(job)
        delete_export_job(job)
        delete_export_job(job)
        self.assertFalse(self.private.exists(self.key))

    def test_orphan_inventory_keeps_live_objects_and_recent_uploads(self):
        self.assertEqual(migrate_export(self.export.pk), "migrated")
        orphan = f"system_intelligence_exports/{uuid4()}/orphan.xlsx"
        self.private.save(orphan, ContentFile(b"orphan"))
        self.assertEqual(list(iter_private_orphans()), [])
        with patch.object(self.private, "get_modified_time", return_value=timezone.now() - timedelta(days=2)):
            self.assertEqual(list(iter_private_orphans()), [orphan])
