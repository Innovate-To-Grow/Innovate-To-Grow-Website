"""Managed exports preserve custom sheet data and require proven row identity."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import BackgroundJob
from apps.event.models import (
    Event,
    Question,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncLog,
    RegistrationSheetSyncRecord,
)
from apps.event.services.registration_sheet_sync import (
    inspect_registration_sheet,
    sync_registrations_to_sheet,
)
from apps.event.services.registration_sheet_sync.worksheet.snapshot import METADATA_PREFIX
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.event.tests.services.registration_sheet.managed.sheet_fakes import FakeWorksheet


class _ManagedRegistrationSheetCase(TestCase):
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


class ManagedRegistrationSheetTests(_ManagedRegistrationSheetCase):
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
