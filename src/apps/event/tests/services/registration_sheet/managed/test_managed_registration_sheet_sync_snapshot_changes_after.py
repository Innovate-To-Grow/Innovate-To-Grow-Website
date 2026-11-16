from copy import deepcopy
from unittest.mock import patch

from django.utils import timezone

from apps.event.models import (
    Event,
    Question,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncLog,
)
from apps.event.services.registration_sheet_sync import (
    create_registration_worksheet,
    inspect_registration_sheet,
    sync_registrations_to_sheet,
)
from apps.event.services.registration_sheet_sync.worksheet.sheets import RegistrationSyncConflict, RegistrationSyncError
from apps.event.tests.services.registration_sheet.managed.test_managed_registration_sheet_sync import (
    _ManagedRegistrationSheetCase,
)


class ManagedRegistrationSheetTests(_ManagedRegistrationSheetCase):
    def test_snapshot_changes_after_preview_block_before_provider_write(self):
        original = self.sheet.get_all_values
        calls = 0

        def changing_values(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.sheet.values = [["Changed during read"]]
            return original(**kwargs)

        with patch.object(self.sheet, "get_all_values", side_effect=changing_values):
            with self.assertRaises(RegistrationSyncError):
                sync_registrations_to_sheet(self.event)
        self.assertFalse(self.sheet.spreadsheet.batches)

    def test_rebuild_preserves_old_sheet_and_switches_only_after_success(self):
        self.sheet.values = [["Unknown legacy header"], ["Do not erase"]]
        original = deepcopy(self.sheet.values)
        preview = inspect_registration_sheet(self.event)
        new_gid = create_registration_worksheet(self.event, expected_fingerprint=preview["fingerprint"])
        self.assertNotEqual(new_gid, self.sheet.id)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_gid, new_gid)
        self.assertEqual(self.sheet.values, original)
        self.assertEqual(len(self.sheet.spreadsheet.backups), 1)
        self.assertEqual(len(self.sheet.spreadsheet.sheets[new_gid].values), 2)

    def test_header_row_and_new_columns_expand_grid_safely(self):
        self.config.header_row = 3
        self.config.save()
        self.sheet.col_count = 2
        self.sheet.values = [["Report title"], [], ["Registration ID", "Notes"], [str(self.registration.pk), "=A1"]]
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[0], ["Report title"])
        self.assertEqual(self.sheet.values[3][1], "=A1")
        self.assertGreater(self.sheet.col_count, 2)

    def test_failure_does_not_replace_later_success_status(self):
        from apps.event.services.registration_sheet_sync.sync.logs import record_sync_failure

        earlier = timezone.now()
        Event.objects.filter(pk=self.event.pk).update(
            registration_sheet_synced_at=timezone.now(), registration_sheet_sync_error=""
        )
        record_sync_failure(self.event, "Earlier failure", cursor_to=earlier)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_error, "")

    def test_inspection_wraps_provider_failure_without_mutating_database(self):
        logs = RegistrationSheetSyncLog.objects.count()
        with patch.object(self.sheet, "get_all_values", side_effect=RuntimeError("Connection failed")):
            with self.assertRaisesRegex(RegistrationSyncError, "Unable to inspect"):
                inspect_registration_sheet(self.event)
        self.assertEqual(RegistrationSheetSyncLog.objects.count(), logs)
        self.assertFalse(self.sheet.spreadsheet.batches)

    def test_missing_managed_header_marker_blocks_reusing_first_participant_as_header(self):
        sync_registrations_to_sheet(self.event)
        self.sheet.values.pop(0)
        self.sheet.metadata = [entry for entry in self.sheet.metadata if entry["metadataValue"] != "__header__"]
        writes = len(self.sheet.spreadsheet.batches)
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(any("header row metadata is missing" in error for error in preview["conflicts"]))
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.spreadsheet.batches), writes)

    def test_id_protection_is_restored_after_warning_only_or_broadened_editors(self):
        sync_registrations_to_sheet(self.event)
        self.sheet.protections[0]["warningOnly"] = True
        self.sheet.protections[0]["editors"] = {"users": ["other@example.com"]}
        sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.protections), 1)
        self.assertFalse(self.sheet.protections[0]["warningOnly"])
        self.assertEqual(self.sheet.protections[0]["editors"], {"users": ["service@example.com"]})

    def test_settings_are_reloaded_after_waiting_for_event_lock(self):
        from apps.event.services.registration_sheet_sync.schedule.state import begin_sync

        def change_after_snapshot(event_id, **kwargs):
            state = begin_sync(event_id, **kwargs)
            RegistrationSheetSyncConfig.objects.filter(event_id=event_id).update(header_row=3)
            return state

        with patch(
            "apps.event.services.registration_sheet_sync.sync.engine.begin_sync", side_effect=change_after_snapshot
        ):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[:2], [[], []])
        self.assertIn(str(self.registration.pk), self.sheet.values[3])

    def test_failure_after_same_generation_success_keeps_event_success(self):
        from apps.event.services.registration_sheet_sync.sync.logs import record_sync_failure

        RegistrationSheetSyncConfig.objects.filter(pk=self.config.pk).update(
            requested_generation=9, completed_generation=9
        )
        record_sync_failure(self.event, "Superseded failure", details={"generation": 9})
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_error, "")

    def test_failed_create_keeps_destination_and_reports_backup_and_populated_new_sheet(self):
        preview = inspect_registration_sheet(self.event)
        with patch(
            "apps.event.services.registration_sheet_sync.sync.create._record_success",
            side_effect=RuntimeError("DB failed"),
        ):
            with self.assertRaises(RegistrationSyncError):
                create_registration_worksheet(self.event, expected_fingerprint=preview["fingerprint"])
        self.event.refresh_from_db()
        self.assertIsNone(self.event.registration_sheet_gid)
        log = RegistrationSheetSyncLog.objects.filter(event=self.event).latest("created_at")
        self.assertTrue(log.details["provider_write_completed"])
        self.assertTrue(log.details["backup_worksheet_gid"])
        self.assertTrue(log.details["created_worksheet_gid"])
        self.assertEqual(log.rows_written, 1)

    def test_deleted_source_after_interrupted_write_requires_explicit_recovery(self):
        with patch(
            "apps.event.services.registration_sheet_sync.sync.engine._record_success",
            side_effect=RuntimeError("DB failed"),
        ):
            with self.assertRaises(RegistrationSyncError):
                sync_registrations_to_sheet(self.event)
        self.registration.delete()
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(any("without a completed sync receipt" in error for error in preview["conflicts"]))
        writes = len(self.sheet.spreadsheet.batches)
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.spreadsheet.batches), writes)

    def test_new_question_never_adopts_existing_custom_column_with_same_label(self):
        sync_registrations_to_sheet(self.event)
        self.sheet.values[0].append("Notes")
        self.sheet.values[1].append("Organizer notes to preserve")
        custom_column = len(self.sheet.values[0])
        question = Question.objects.create(event=self.event, text="Notes")
        self.registration.question_answers = [
            {"question_id": str(question.pk), "question_text": "Notes", "answer": "Participant answer"}
        ]
        self.registration.save()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][custom_column - 1], "Organizer notes to preserve")
        managed_column = self.column(f"question:{question.pk}")
        self.assertGreater(managed_column, 26)
        self.assertEqual(self.sheet.values[1][managed_column - 1], "Participant answer")

    def test_lost_field_metadata_never_rebinds_matching_custom_values(self):
        sync_registrations_to_sheet(self.event)
        original_column = self.column("first_name")
        self.sheet.metadata = [entry for entry in self.sheet.metadata if entry["metadataValue"] != "first_name"]
        self.sheet.values[1][original_column - 1] = "Preserve orphaned column"
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][original_column - 1], "Preserve orphaned column")
        self.assertGreater(self.column("first_name"), 26)
