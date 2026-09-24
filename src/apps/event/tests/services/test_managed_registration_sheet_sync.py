"""Managed exports preserve custom sheet data and require proven row identity."""

import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.event.models import (
    Event,
    Question,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncLog,
    RegistrationSheetSyncRecord,
)
from apps.event.services.registration_sheet_sync import (
    create_registration_worksheet,
    inspect_registration_sheet,
    sync_registrations_to_sheet,
)
from apps.event.services.registration_sheet_sync.provider import METADATA_PREFIX
from apps.event.services.registration_sheet_sync.schema import registration_fields, registration_values
from apps.event.services.registration_sheet_sync.sheets import RegistrationSyncConflict, RegistrationSyncError
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.event.tests.services.sheet_fakes import FakeWorksheet


class ManagedRegistrationSheetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.event = make_event(collect_phone=True, allow_secondary_email=True)
        Event.objects.filter(pk=self.event.pk).update(registration_sheet_id="test-sheet")
        self.event.refresh_from_db()
        self.config, _ = RegistrationSheetSyncConfig.objects.get_or_create(
            event=self.event, defaults={"sync_mode": "manual"}
        )
        self.config.sync_mode = "manual"
        self.config.save()
        self.ticket = make_ticket(self.event)
        self.member = make_member(first_name="Ada", last_name="Lovelace")
        self.registration = make_registration(self.member, self.event, self.ticket, attendee_phone="+12095551234")
        self.sheet = FakeWorksheet()
        self.credentials = SimpleNamespace(
            is_configured=True, get_credentials_info=lambda: {"client_email": "service@example.com"}
        )
        for name, value in (("GoogleCredentialConfig.load", self.credentials), ("_get_worksheet", self.sheet)):
            mock = patch(f"apps.event.services.registration_sheet_sync.{name}", return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def column(self, key):
        return next(
            item["location"]["dimensionRange"]["startIndex"] + 1
            for item in self.sheet.metadata
            if item["metadataKey"] == f"{METADATA_PREFIX}{self.event.pk}" and item["metadataValue"] == key
        )

    def test_inspection_is_read_only_and_supports_unsaved_draft(self):
        before = (
            BackgroundJob.objects.count(),
            RegistrationSheetSyncLog.objects.count(),
            RegistrationSheetSyncRecord.objects.count(),
        )
        draft = deepcopy(self.config)
        draft.header_row = 3
        draft.field_settings = {"first_name": {"label": "Given name"}}
        preview = inspect_registration_sheet(self.event, config=draft)
        self.assertEqual(preview["connection"]["header_row"], 3)
        self.assertEqual(preview["counts"]["added"], 1)
        self.assertTrue(preview["can_sync"])
        self.assertEqual(
            before,
            (
                BackgroundJob.objects.count(),
                RegistrationSheetSyncLog.objects.count(),
                RegistrationSheetSyncRecord.objects.count(),
            ),
        )
        self.assertFalse(self.sheet.spreadsheet.batches)
        self.assertFalse(self.sheet.spreadsheet.backups)
        self.config.refresh_from_db()
        self.assertEqual(self.config.header_row, 1)

    def test_empty_sheet_initializes_without_registrations(self):
        self.registration.delete()
        self.assertEqual(sync_registrations_to_sheet(self.event), 0)
        self.assertEqual(self.sheet.values[0][self.column("registration_id") - 1], "Registration ID")
        self.assertIn(self.column("registration_id"), self.sheet.hidden)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_count, 0)

    def test_upsert_preserves_custom_columns_and_updates_same_registration(self):
        self.assertEqual(sync_registrations_to_sheet(self.event), 1)
        self.sheet.values[0].append("Notes")
        self.sheet.values[1].append("=SUM(A2:A9)")
        notes = len(self.sheet.values[0]) - 1
        self.registration.attendee_first_name = "Grace"
        self.registration.save(update_fields=["attendee_first_name", "updated_at"])
        self.assertEqual(sync_registrations_to_sheet(self.event), 1)
        self.assertEqual(self.sheet.values[1][self.column("first_name") - 1], "Grace")
        self.assertEqual(self.sheet.values[1][notes], "=SUM(A2:A9)")
        self.assertEqual(len(self.sheet.values), 2)
        self.assertEqual(sync_registrations_to_sheet(self.event), 0)
        self.assertEqual(RegistrationSheetSyncLog.objects.first().details["unchanged"], 1)

    def test_visible_rename_and_reordered_id_column_use_metadata(self):
        sync_registrations_to_sheet(self.event)
        first = self.column("first_name") - 1
        identity = self.column("registration_id") - 1
        self.sheet.values[0][first] = "Attendee given name"
        for row in self.sheet.values:
            row[first], row[identity] = row[identity], row[first]
        for item in self.sheet.metadata:
            dimension = item["location"]["dimensionRange"]
            if dimension["dimension"] == "COLUMNS" and dimension["startIndex"] in (first, identity):
                dimension["startIndex"] = identity if dimension["startIndex"] == first else first
                dimension["endIndex"] = dimension["startIndex"] + 1
        self.registration.attendee_first_name = "Changed"
        self.registration.save()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[0][identity], "Attendee given name")
        self.assertEqual(self.sheet.values[1][identity], "Changed")
        self.assertEqual(self.sheet.values[1][first], str(self.registration.pk))

    def test_custom_label_applies_once_then_sheet_rename_is_preserved(self):
        self.config.field_settings = {"first_name": {"label": "Given"}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        column = self.column("first_name") - 1
        self.assertEqual(self.sheet.values[0][column], "Given")
        self.sheet.values[0][column] = "Sheet renamed this"
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[0][column], "Sheet renamed this")
        self.config.field_settings = {"first_name": {"label": "Admin changed this"}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[0][column], "Admin changed this")

    def test_disabled_field_column_and_custom_formula_are_retained(self):
        sync_registrations_to_sheet(self.event)
        column = self.column("phone") - 1
        self.sheet.values[1][column] = "Keep this value"
        self.config.field_settings = {"phone": {"enabled": False}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][column], "Keep this value")

    def test_formula_like_headers_values_and_phones_are_raw_strings(self):
        question = Question.objects.create(event=self.event, text='=IMPORTDATA("bad")')
        self.registration.question_answers = [
            {"question_id": str(question.pk), "question_text": question.text, "answer": "=1+1"}
        ]
        self.registration.attendee_first_name = "00123"
        self.registration.save()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][self.column("phone") - 1], "+12095551234")
        self.assertEqual(self.sheet.values[1][self.column("first_name") - 1], "00123")
        self.assertEqual(self.sheet.values[1][self.column(f"question:{question.pk}") - 1], "=1+1")
        for request in self.sheet.spreadsheet.batches[-1]["requests"]:
            if "updateCells" in request:
                self.assertEqual(request["updateCells"]["fields"], "userEnteredValue")
                for row in request["updateCells"]["rows"]:
                    self.assertEqual(set(row["values"][0]["userEnteredValue"]), {"stringValue"})

    def test_question_identity_survives_rename_and_duplicate_labels_require_mapping(self):
        question = Question.objects.create(event=self.event, text="First question")
        self.registration.question_answers = [
            {"question_id": str(question.pk), "question_text": "Old question", "answer": "Stored answer"}
        ]
        self.registration.save()
        sync_registrations_to_sheet(self.event)
        column = self.column(f"question:{question.pk}") - 1
        question.text = "Renamed question"
        question.save()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][column], "Stored answer")
        self.assertEqual(self.sheet.values[0][column], "First question")

    def test_duplicate_metadata_or_ids_block_all_writes(self):
        sync_registrations_to_sheet(self.event)
        count = len(self.sheet.spreadsheet.batches)
        copied = deepcopy(self.sheet.metadata[0])
        copied["metadataId"] = 999
        self.sheet.metadata.append(copied)
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.spreadsheet.batches), count)
        self.sheet.metadata.pop()
        self.sheet.values.append(list(self.sheet.values[1]))
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(preview["conflicts"])
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.spreadsheet.batches), count)

    def test_unknown_registration_id_is_not_deleted_or_overwritten(self):
        self.sheet.values = [["Registration ID", "Notes"], [str(uuid.uuid4()), "Keep me"]]
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        self.assertFalse(self.sheet.spreadsheet.batches)

    def test_other_event_metadata_blocks_shared_destination(self):
        self.sheet.metadata = [
            {
                "metadataId": 1,
                "metadataKey": f"{METADATA_PREFIX}{uuid.uuid4()}",
                "metadataValue": "registration_id",
                "location": {
                    "dimensionRange": {"sheetId": self.sheet.id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}
                },
            }
        ]
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)

    def test_unrecognized_populated_legacy_headers_never_append_duplicates(self):
        self.sheet.values = [["Email", "Name"], ["test@example.com", "Ada Lovelace"]]
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(preview["conflicts"])
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        self.assertFalse(self.sheet.spreadsheet.batches)

    def test_legacy_adoption_requires_current_preview_and_backup(self):
        self.sheet.values = [["Ticket Code", "Notes"], [self.registration.ticket_code, "=1+1"]]
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(preview["requires_adoption"])
        self.assertEqual(preview["legacy_matches"][0]["registration_id"], str(self.registration.pk))
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event, adopt_legacy=True)
        sync_registrations_to_sheet(self.event, adopt_legacy=True, expected_fingerprint=preview["fingerprint"])
        self.assertEqual(len(self.sheet.spreadsheet.backups), 1)
        self.assertEqual(len(self.sheet.values), 2)
        self.assertEqual(self.sheet.values[1][1], "=1+1")
        self.assertEqual(self.sheet.values[1][self.column("registration_id") - 1], str(self.registration.pk))

    def test_five_field_legacy_match_is_exact_and_one_to_one(self):
        values = registration_values(self.registration, self.event, 1, registration_fields(self.event))
        keys = ["created_at", "primary_email", "ticket_type", "first_name", "last_name"]
        self.sheet.values = [
            ["When Started", "Membership Primary", "Ticket Type", "First Name", "Last Name"],
            [values[key] for key in keys],
        ]
        self.assertTrue(inspect_registration_sheet(self.event)["requires_adoption"])
        self.sheet.values.append(list(self.sheet.values[1]))
        self.assertTrue(inspect_registration_sheet(self.event)["conflicts"])

    def test_ambiguous_headers_require_explicit_mapping(self):
        self.sheet.values = [
            ["Registration ID", "First Name", "First Name"],
            [str(self.registration.pk), "Ada", "Manual notes"],
        ]
        self.assertTrue(inspect_registration_sheet(self.event)["conflicts"])
        self.config.column_mappings = {"first_name": 2}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][2], "Manual notes")

    def test_known_deleted_registration_is_marked_and_notes_remain(self):
        sync_registrations_to_sheet(self.event)
        self.sheet.values[0].append("Notes")
        self.sheet.values[1].append("Retain deleted row notes")
        self.registration.delete()
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][self.column("status") - 1], "Deleted")
        self.assertEqual(self.sheet.values[1][-1], "Retain deleted row notes")

    def test_provider_success_then_db_failure_retries_by_id_without_duplicate(self):
        with patch(
            "apps.event.services.registration_sheet_sync.engine._record_success",
            side_effect=RuntimeError("db unavailable"),
        ):
            with self.assertRaises(RegistrationSyncError):
                sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.values), 2)
        sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.values), 2)
        self.assertTrue(
            RegistrationSheetSyncRecord.objects.filter(
                event=self.event, registration_id=self.registration.pk, synced_at__isnull=False
            ).exists()
        )

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
        from apps.event.services.registration_sheet_sync.logs import record_sync_failure

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
        from apps.event.services.registration_sheet_sync.scheduler import begin_sync

        def change_after_snapshot(event_id, **kwargs):
            state = begin_sync(event_id, **kwargs)
            RegistrationSheetSyncConfig.objects.filter(event_id=event_id).update(header_row=3)
            return state

        with patch("apps.event.services.registration_sheet_sync.engine.begin_sync", side_effect=change_after_snapshot):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[:2], [[], []])
        self.assertIn(str(self.registration.pk), self.sheet.values[3])

    def test_failure_after_same_generation_success_keeps_event_success(self):
        from apps.event.services.registration_sheet_sync.logs import record_sync_failure

        RegistrationSheetSyncConfig.objects.filter(pk=self.config.pk).update(
            requested_generation=9, completed_generation=9
        )
        record_sync_failure(self.event, "Superseded failure", details={"generation": 9})
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_sync_error, "")

    def test_failed_create_keeps_destination_and_reports_backup_and_populated_new_sheet(self):
        preview = inspect_registration_sheet(self.event)
        with patch(
            "apps.event.services.registration_sheet_sync.engine._record_success", side_effect=RuntimeError("DB failed")
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
            "apps.event.services.registration_sheet_sync.engine._record_success", side_effect=RuntimeError("DB failed")
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

    def test_orphaned_label_metadata_is_managed_and_blocks_bootstrap(self):
        self.config.field_settings = {"first_name": {"label": "Given"}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        self.sheet.metadata = [entry for entry in self.sheet.metadata if "registration-label" in entry["metadataKey"]]
        writes = len(self.sheet.spreadsheet.batches)
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(any("ID column metadata is missing" in error for error in preview["conflicts"]))
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.spreadsheet.batches), writes)

    def test_explicit_mapping_cannot_take_over_new_field_on_managed_sheet(self):
        sync_registrations_to_sheet(self.event)
        self.sheet.values[0].append("Custom organization")
        self.sheet.values[1].append("Preserve me")
        self.config.field_settings = {"organization": {"enabled": True}}
        self.config.column_mappings = {"organization": len(self.sheet.values[0])}
        self.config.save()
        with self.assertRaisesRegex(RegistrationSyncConflict, "only to initial setup"):
            sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.values[1][-1], "Preserve me")

    def test_default_first_worksheet_selection_is_pinned_only_after_success(self):
        self.assertIsNone(self.event.registration_sheet_gid)
        inspect_registration_sheet(self.event)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.registration_sheet_gid)
        sync_registrations_to_sheet(self.event)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_gid, self.sheet.id)
