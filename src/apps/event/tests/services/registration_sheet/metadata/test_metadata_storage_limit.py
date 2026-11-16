"""A write Google rejects for metadata storage fails with a clear error; the production job path recovers."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from gspread.exceptions import APIError

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs.worker import claim_jobs, process_claimed_job
from apps.event.models import RegistrationSheetSyncConfig, RegistrationSheetSyncLog
from apps.event.services.registration_sheet_sync import schedule_registration_sync, sync_registrations_to_sheet
from apps.event.services.registration_sheet_sync.worksheet.batch_updates import METADATA_STORAGE_FULL
from apps.event.services.registration_sheet_sync.worksheet.sheets import RegistrationSyncError
from apps.event.tests.helpers import make_registration
from apps.event.tests.services.registration_sheet.managed.sheet_fakes import api_error
from apps.event.tests.services.registration_sheet.managed.test_managed_registration_sheet_sync import (
    _ManagedRegistrationSheetCase,
)
from apps.event.tests.services.registration_sheet.managed.test_registration_sheet_sync_race import _ManagedSyncRaceCase
from apps.event.tests.services.registration_sheet.metadata.old_reader import add_other_tool_metadata, fill_to_limit


class StorageLimitTests(_ManagedRegistrationSheetCase):
    def test_a_full_sheet_is_reported_clearly_and_nothing_is_written(self):
        add_other_tool_metadata(self.sheet, room=100)
        before = deepcopy(self.sheet.metadata)

        with self.assertRaises(RegistrationSyncError) as raised:
            sync_registrations_to_sheet(self.event)

        self.assertEqual(str(raised.exception), METADATA_STORAGE_FULL)
        self.assertIsInstance(raised.exception.__cause__, APIError)
        self.assertEqual((self.sheet.values, self.sheet.metadata), ([], before))
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_error, METADATA_STORAGE_FULL)
        log = RegistrationSheetSyncLog.objects.get(event=self.event)
        self.assertEqual(
            (log.status, log.error_message), (RegistrationSheetSyncLog.Status.FAILED, METADATA_STORAGE_FULL)
        )
        self.assertFalse(log.details["provider_write_completed"])
        # Failed, not blocked: the next registration change queues a sync, as for any other provider error.
        config = RegistrationSheetSyncConfig.objects.get(event=self.event)
        self.assertEqual(config.state, RegistrationSheetSyncConfig.State.FAILED)

    def test_other_provider_errors_keep_their_message(self):
        error = api_error("Invalid requests[3].updateCells: The range is out of bounds.")
        with patch.object(self.sheet.spreadsheet, "batch_update", side_effect=error):
            with self.assertRaisesRegex(
                RegistrationSyncError, r"^Failed to write to Google Sheet: APIError: \[400\]: Invalid requests\[3\]"
            ):
                sync_registrations_to_sheet(self.event)


class StorageLimitJobTests(_ManagedSyncRaceCase):
    """The production path: worker -> job handler -> _flush_pending_sync -> engine -> one batchUpdate."""

    def run_job(self):
        job = schedule_registration_sync(self.event, immediate=True)
        BackgroundJob.objects.filter(pk=job.pk).update(available_at=timezone.now() - timedelta(seconds=1))
        claimed = next(item for item in claim_jobs(batch_size=100) if item.pk == job.pk)
        succeeded = process_claimed_job(claimed)
        claimed.refresh_from_db()
        return succeeded, claimed

    def test_the_failing_job_succeeds_on_a_sheet_the_old_reader_filled(self):
        registration = make_registration(self.member, self.event, self.ticket)
        self.assertTrue(self.run_job()[0])
        clean = deepcopy(self.sheet.metadata)
        fill_to_limit(self.sheet)
        registration.attendee_first_name = "Grace"
        registration.save()

        succeeded, job = self.run_job()

        self.assertTrue(succeeded, job.last_error)
        self.assertEqual(self.sheet.metadata, clean)
        self.assertIn("Grace", self.sheet.values[1])

    def test_a_job_on_a_full_sheet_fails_with_the_clear_error(self):
        make_registration(self.member, self.event, self.ticket)
        add_other_tool_metadata(self.sheet, room=100)

        succeeded, job = self.run_job()

        self.assertFalse(succeeded)
        self.assertEqual((job.status, job.last_error), (BackgroundJob.Status.FAILED, METADATA_STORAGE_FULL))
