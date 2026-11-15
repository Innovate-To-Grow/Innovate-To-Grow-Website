from apps.event.services.registration_sheet_sync import (
    inspect_registration_sheet,
    sync_registrations_to_sheet,
)
from apps.event.services.registration_sheet_sync.worksheet.sheets import RegistrationSyncConflict
from apps.event.tests.services.registration_sheet.managed.test_managed_registration_sheet_sync import (
    _ManagedRegistrationSheetCase,
)


class ManagedRegistrationSheetTests(_ManagedRegistrationSheetCase):
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
