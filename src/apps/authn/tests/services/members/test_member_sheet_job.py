from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import enqueue_job


class MemberSheetSyncJobTests(TestCase):
    @patch("apps.authn.services.members.sheet_sync._flush_pending_sync")
    def test_member_sheet_handler_cancels_only_pre_claim_duplicates(self, flush):
        from apps.authn.services.members.sheet_sync.jobs import sync_member_sheet_job

        claimed_at = timezone.now()
        current, _created = enqueue_job(
            kind="authn.member_sheet_sync",
            dedupe_key="current",
            payload={},
        )
        older, _created = enqueue_job(
            kind="authn.member_sheet_sync",
            dedupe_key="older",
            payload={},
        )
        newer, _created = enqueue_job(
            kind="authn.member_sheet_sync",
            dedupe_key="newer",
            payload={},
        )
        BackgroundJob.objects.filter(pk=older.pk).update(created_at=claimed_at - timedelta(seconds=1))
        BackgroundJob.objects.filter(pk=newer.pk).update(created_at=claimed_at + timedelta(seconds=1))

        sync_member_sheet_job(SimpleNamespace(pk=current.pk, claimed_at=claimed_at))

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(older.status, BackgroundJob.Status.CANCELLED)
        self.assertEqual(newer.status, BackgroundJob.Status.PENDING)
        flush.assert_called_once_with(raise_errors=True)
