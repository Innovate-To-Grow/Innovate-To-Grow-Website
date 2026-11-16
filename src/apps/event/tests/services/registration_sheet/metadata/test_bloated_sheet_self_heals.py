"""A worksheet the old reader filled with copies recovers on its next sync, in one write, without manual steps."""

from copy import deepcopy

from gspread.exceptions import APIError

from apps.event.models import RegistrationSheetSyncLog
from apps.event.services.registration_sheet_sync import inspect_registration_sheet, sync_registrations_to_sheet
from apps.event.services.registration_sheet_sync.worksheet.sheets import RegistrationSyncConflict
from apps.event.tests.services.registration_sheet.managed.sheet_fakes import METADATA_LIMIT, metadata_size
from apps.event.tests.services.registration_sheet.managed.test_managed_registration_sheet_sync import (
    _ManagedRegistrationSheetCase,
)
from apps.event.tests.services.registration_sheet.metadata.old_reader import add_copies, fill_to_limit, old_reader_run


class BloatedSheetTests(_ManagedRegistrationSheetCase):
    def setUp(self):
        super().setUp()
        self.config.field_settings = {"first_name": {"label": "Given"}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        self.clean = deepcopy(self.sheet.metadata)

    def entry(self, value):
        return next(entry for entry in self.clean if entry["metadataValue"] == value)

    def test_a_sheet_filled_to_the_limit_recovers_in_one_write(self):
        entries, runs = fill_to_limit(self.sheet)
        self.assertGreater(runs, 10)
        self.assertGreater(metadata_size(self.sheet.metadata), METADATA_LIMIT - metadata_size(entries))
        # The next old-reader run no longer fits: the write Google rejected in production.
        with self.assertRaisesRegex(APIError, "exceed the allowed storage limit"):
            self.sheet.spreadsheet.batch_update({"requests": old_reader_run(entries)})
        writes = len(self.sheet.spreadsheet.batches)
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(preview["can_sync"])
        self.assertEqual(len(self.sheet.spreadsheet.batches), writes)
        self.registration.attendee_first_name = "Grace"
        self.registration.save()

        sync_registrations_to_sheet(self.event)

        self.assertEqual(len(self.sheet.spreadsheet.batches), writes + 1)
        requests = self.sheet.spreadsheet.batches[-1]["requests"]
        copies = len(entries) * runs
        # Every copy is deleted first, and nothing is created: the write only ever frees storage.
        self.assertTrue(all("deleteDeveloperMetadata" in request for request in requests[:copies]))
        self.assertEqual([name for request in requests[copies:] for name in request if "DeveloperMetadata" in name], [])
        self.assertEqual(self.sheet.metadata, self.clean)
        self.assertEqual(self.sheet.values[1][self.column("first_name") - 1], "Grace")
        log = RegistrationSheetSyncLog.objects.filter(event=self.event).latest("created_at")
        self.assertEqual(
            (log.status, log.details["metadata_removed"]), (RegistrationSheetSyncLog.Status.SUCCESS, copies)
        )
        sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.metadata, self.clean)

    def test_a_field_bound_again_after_a_header_rename_keeps_the_column_written_last(self):
        old = self.column("first_name")
        self.sheet.values[0][old - 1] = "Organizer notes"
        self.sheet.values[1][old - 1] = "Call back on Tuesday"
        # The old reader no longer found the field's label, appended a column for it and bound it there; it bound
        # every other column again where it was.
        new = self.sheet.col_count + 1
        self.sheet.col_count = new
        self.sheet.values[0].extend([""] * (new - len(self.sheet.values[0]) - 1) + ["Given"])
        self.sheet.values[1].extend([""] * (new - len(self.sheet.values[1]) - 1) + ["Ada"])
        moved = deepcopy(self.entry("first_name"))
        moved["location"]["dimensionRange"].update(startIndex=new - 1, endIndex=new)
        add_copies(self.sheet, [moved, *(entry for entry in self.clean if entry["metadataValue"] != "first_name")], 2)
        self.registration.attendee_first_name = "Grace"
        self.registration.save()

        sync_registrations_to_sheet(self.event)

        self.assertEqual(self.column("first_name"), new)
        self.assertEqual(self.sheet.values[1][new - 1], "Grace")
        self.assertEqual(self.sheet.values[0][old - 1], "Organizer notes")
        self.assertEqual(self.sheet.values[1][old - 1], "Call back on Tuesday")
        self.assertEqual(len(self.sheet.metadata), len(self.clean))

    def test_copies_at_columns_no_longer_headed_by_the_field_still_block(self):
        old = self.column("first_name")
        self.sheet.values[0][old - 1] = "Organizer notes"
        self.sheet.values[0].append("Notes")
        other = deepcopy(self.entry("first_name"))
        other["location"]["dimensionRange"].update(
            startIndex=len(self.sheet.values[0]) - 1, endIndex=len(self.sheet.values[0])
        )
        add_copies(self.sheet, [other], 2)
        writes = len(self.sheet.spreadsheet.batches)

        with self.assertRaisesRegex(
            RegistrationSyncConflict, "Duplicate or invalid managed column binding: first_name"
        ):
            sync_registrations_to_sheet(self.event)

        self.assertEqual(len(self.sheet.spreadsheet.batches), writes)

    def test_old_header_row_markers_and_label_copies_go_and_a_later_header_rename_stays(self):
        column = self.column("first_name")
        self.sheet.values[0][column - 1] = "Preferred name"
        marker = deepcopy(self.entry("__header__"))
        marker["location"]["dimensionRange"].update(startIndex=2, endIndex=3)
        label = next(entry for entry in self.clean if "registration-label" in entry["metadataKey"])
        older = {**deepcopy(label), "metadataValue": '{"key":"first_name","label":"First name (old)"}'}
        add_copies(self.sheet, [marker, older, self.entry("__header__"), label], 3)

        sync_registrations_to_sheet(self.event)

        self.assertEqual(self.sheet.metadata, self.clean)
        self.assertEqual(self.sheet.values[0][column - 1], "Preferred name")
