"""Repeated syncs reuse the worksheet's developer metadata instead of adding to it."""

import json
from copy import deepcopy

from apps.event.models import Question, RegistrationSheetSyncLog
from apps.event.services.registration_sheet_sync import inspect_registration_sheet, sync_registrations_to_sheet
from apps.event.tests.helpers import make_member, make_registration
from apps.event.tests.services.registration_sheet.managed.sheet_fakes import metadata_size
from apps.event.tests.services.registration_sheet.managed.test_managed_registration_sheet_sync import (
    _ManagedRegistrationSheetCase,
)


def _metadata_writes(batch):
    names = ("createDeveloperMetadata", "updateDeveloperMetadata", "deleteDeveloperMetadata")
    return [request for request in batch["requests"] if any(name in request for name in names)]


class MetadataStaysBoundedTests(_ManagedRegistrationSheetCase):
    def labels(self):
        return [entry for entry in self.sheet.metadata if "registration-label" in entry["metadataKey"]]

    def test_repeated_syncs_reuse_the_entries_of_the_first(self):
        self.config.field_settings = {"first_name": {"label": "Given"}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        first = deepcopy(self.sheet.metadata)
        purposes = {(entry["metadataKey"], entry["metadataValue"]) for entry in first}
        self.assertEqual(len(purposes), len(first))
        for name in ("Grace", "Barbara", "Katherine"):
            self.registration.attendee_first_name = name
            self.registration.save()
            make_registration(make_member(f"{name.lower()}@example.com"), self.event, self.ticket)
            sync_registrations_to_sheet(self.event)
        self.assertEqual(self.sheet.metadata, first)
        self.assertEqual(len(self.sheet.values), 5)
        for batch in self.sheet.spreadsheet.batches[1:]:
            self.assertEqual(_metadata_writes(batch), [])
        self.assertEqual(
            RegistrationSheetSyncLog.objects.filter(event=self.event).latest("created_at").details["metadata_removed"],
            0,
        )

    def test_a_label_change_updates_its_entry_in_place(self):
        self.config.field_settings = {"first_name": {"label": "Given"}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        (label,) = self.labels()
        self.assertEqual(label["metadataValue"], '{"key":"first_name","label":"Given"}')
        size = metadata_size(self.sheet.metadata)
        self.config.field_settings = {"first_name": {"label": "Attendee first name"}}
        self.config.save()
        sync_registrations_to_sheet(self.event)
        (updated,) = self.labels()
        self.assertEqual(updated["metadataId"], label["metadataId"])
        self.assertEqual(json.loads(updated["metadataValue"]), {"key": "first_name", "label": "Attendee first name"})
        self.assertEqual(metadata_size(self.sheet.metadata), size + len("Attendee first name") - len("Given"))
        self.assertEqual(self.sheet.values[0][self.column("first_name") - 1], "Attendee first name")

    def test_a_deleted_question_releases_its_column_binding_and_keeps_the_column(self):
        question = Question.objects.create(event=self.event, text="T-shirt size")
        key = f"question:{question.pk}"
        self.registration.question_answers = [
            {"question_id": str(question.pk), "question_text": question.text, "answer": "M"}
        ]
        self.registration.save()
        sync_registrations_to_sheet(self.event)
        column = self.column(key)
        count = len(self.sheet.metadata)
        question.delete()
        preview = inspect_registration_sheet(self.event)
        self.assertTrue(preview["can_sync"])
        self.assertEqual(len(self.sheet.metadata), count)
        sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.metadata), count - 1)
        self.assertFalse([entry for entry in self.sheet.metadata if entry["metadataValue"] == key])
        self.assertEqual((self.sheet.values[0][column - 1], self.sheet.values[1][column - 1]), ("T-shirt size", "M"))
        log = RegistrationSheetSyncLog.objects.filter(event=self.event).latest("created_at")
        self.assertEqual(log.details["metadata_removed"], 1)
        sync_registrations_to_sheet(self.event)
        self.assertEqual(len(self.sheet.metadata), count - 1)
