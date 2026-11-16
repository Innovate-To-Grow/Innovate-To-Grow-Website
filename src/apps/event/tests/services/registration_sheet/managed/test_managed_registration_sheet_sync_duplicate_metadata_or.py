import uuid
from copy import deepcopy
from unittest.mock import patch

from apps.event.models import (
    RegistrationSheetSyncRecord,
)
from apps.event.services.registration_sheet_sync import (
    inspect_registration_sheet,
    sync_registrations_to_sheet,
)
from apps.event.services.registration_sheet_sync.plan.schema import registration_fields, registration_values
from apps.event.services.registration_sheet_sync.worksheet.sheets import RegistrationSyncConflict, RegistrationSyncError
from apps.event.services.registration_sheet_sync.worksheet.snapshot import METADATA_PREFIX
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.event.tests.services.registration_sheet.managed.test_managed_registration_sheet_sync import (
    _ManagedRegistrationSheetCase,
)


class ManagedRegistrationSheetTests(_ManagedRegistrationSheetCase):
    def test_copied_metadata_is_removed_but_duplicate_ids_block_all_writes(self):
        sync_registrations_to_sheet(self.event)
        original = deepcopy(self.sheet.metadata)
        copied = deepcopy(self.sheet.metadata[0])
        copied["metadataId"] = 999
        self.sheet.metadata.append(copied)
        # An exact copy carries nothing the original does not: the next sync deletes it instead of stopping.
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.metadata, original)
        count = len(self.sheet.spreadsheet.batches)
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

    def test_legacy_rows_for_deleted_registrations_are_adopted_as_deleted(self):
        stale_id = str(uuid.uuid4())
        self.sheet.values = [
            ["Registration Status", "Notes", "Registration ID"],
            ["Active", "Keep me", str(self.registration.pk)],
            ["Active", "Removed before receipts", stale_id],
        ]
        preview = inspect_registration_sheet(self.event)
        self.assertFalse(preview["conflicts"])
        self.assertTrue(preview["requires_adoption"])
        self.assertEqual(preview["stale_rows"], [{"row": 3, "registration_id": stale_id}])
        with self.assertRaises(RegistrationSyncConflict):
            sync_registrations_to_sheet(self.event)
        sync_registrations_to_sheet(self.event, adopt_legacy=True, expected_fingerprint=preview["fingerprint"])
        self.assertEqual(len(self.sheet.spreadsheet.backups), 1)
        self.assertEqual(self.sheet.values[2][self.column("status") - 1], "Deleted")
        self.assertEqual(self.sheet.values[2][1], "Removed before receipts")
        record = RegistrationSheetSyncRecord.objects.get(event=self.event, registration_id=stale_id)
        self.assertIsNotNone(record.synced_at)
        self.assertIsNotNone(record.deleted_at)
        # Later managed syncs recognize the adopted row instead of blocking on it.
        self.assertTrue(inspect_registration_sheet(self.event)["can_sync"])
        sync_registrations_to_sheet(self.event)

    def test_legacy_row_for_other_event_registration_blocks_adoption(self):
        other_event = make_event(name="Other")
        other = make_registration(
            make_member("grace@example.com", first_name="Grace"), other_event, make_ticket(other_event)
        )
        self.sheet.values = [["Registration ID"], [str(self.registration.pk)], [str(other.pk)]]
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(any("different event" in error for error in preview["conflicts"]))

    def test_unknown_registration_id_on_managed_sheet_still_blocks(self):
        sync_registrations_to_sheet(self.event)
        row = [""] * len(self.sheet.values[0])
        row[self.column("registration_id") - 1] = str(uuid.uuid4())
        self.sheet.values.append(row)
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(any("unknown Registration ID" in error for error in preview["conflicts"]))
        self.assertFalse(preview["stale_rows"])

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
            "apps.event.services.registration_sheet_sync.sync.engine._record_success",
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
