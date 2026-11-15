import copy
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.event.models import RegistrationSheetSyncConfig
from apps.event.services import registration_sheet_sync as sync_api
from apps.event.tests.helpers import make_event, make_superuser

FIELDS = [
    {"key": "first_name", "label": "First Name", "enabled": True},
    {"key": "organization", "label": "Organization", "enabled": False},
    {"key": "registration_id", "label": "Registration ID", "enabled": True},
    {"key": "status", "label": "Registration Status", "enabled": True},
]
PREVIEW = {
    "connection": {"sheet_id": "test-sheet", "worksheet_id": 7, "worksheet_title": "Registrations", "header_row": 1},
    "columns": [
        {"key": "first_name", "label": "First Name", "column": 1, "managed": True, "enabled": True, "action": "Keep"}
    ],
    "existing_columns": [{"column": 1, "label": "First Name"}, {"column": 2, "label": "Notes"}],
    "counts": {"added": 1, "updated": 2, "deleted": 0, "unchanged": 3, "header_changes": 0},
    "conflicts": [],
    "legacy_matches": [],
    "requires_adoption": False,
    "can_sync": True,
    "fingerprint": "sheet-snapshot-1",
}


class _RegistrationSheetSyncAdminCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.scheduler_patch = patch.object(sync_api, "schedule_registration_sync")
        self.scheduler = self.scheduler_patch.start()
        self.addCleanup(self.scheduler_patch.stop)
        self.schema_patch = patch.object(
            sync_api, "available_registration_fields", return_value=copy.deepcopy(FIELDS), create=True
        )
        self.schema_patch.start()
        self.addCleanup(self.schema_patch.stop)
        self.inspect_patch = patch.object(
            sync_api, "inspect_registration_sheet", return_value=copy.deepcopy(PREVIEW), create=True
        )
        self.inspect = self.inspect_patch.start()
        self.addCleanup(self.inspect_patch.stop)
        self.sync_patch = patch.object(sync_api, "sync_registrations_to_sheet", return_value=3)
        self.sync = self.sync_patch.start()
        self.addCleanup(self.sync_patch.stop)
        self.create_patch = patch.object(sync_api, "create_registration_worksheet", return_value=42, create=True)
        self.create = self.create_patch.start()
        self.addCleanup(self.create_patch.stop)
        self.user = make_superuser()
        self.client.force_login(self.user)
        self.event = make_event(name="Sync Showcase", registration_sheet_id="test-sheet", registration_sheet_gid=7)
        self.url = reverse("admin:event_event_sheet_sync", args=[self.event.pk])
        self.scheduler.reset_mock()

    def settings_data(self, **overrides):
        values = {
            "action": "save_settings",
            "spreadsheet": "test-sheet",
            "worksheet_id": "7",
            "sync_mode": "manual",
            "interval_minutes": "5",
            "header_row": "1",
        }
        for index, field in enumerate(FIELDS):
            values[f"field_{index}_label"] = field["label"]
            values[f"field_{index}_column"] = ""
            if field["enabled"]:
                values[f"field_{index}_enabled"] = "on"
        values.update(overrides)
        return values

    def config(self, **overrides):
        return RegistrationSheetSyncConfig.objects.create(event=self.event, **overrides)

    def review_token(self, operation):
        if operation == "adoption":
            self.inspect.return_value = {
                **copy.deepcopy(PREVIEW),
                "requires_adoption": True,
                "can_sync": False,
                "legacy_matches": [{"row": 2, "registration_id": "registration-1", "ticket_code": "I2G-001"}],
            }
        response = self.client.post(self.url, {"action": f"review_{operation}"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review before continuing")
        return response.context["review"]["token"]


class RegistrationSheetSyncAdminTest(_RegistrationSheetSyncAdminCase):
    def test_get_is_database_only_and_does_not_create_configuration(self):
        response = self.client.get(self.url, {"action": "sync_now"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration sheet sync")
        self.assertContains(response, "Save settings")
        self.assertContains(response, "Preview changes")
        self.assertContains(response, "15 seconds")
        self.assertContains(response, "60 seconds")
        self.assertNotContains(response, "textarea")
        self.assertContains(response, 'aria-label="Include First Name"')
        self.assertContains(response, 'aria-label="First Name column label"')
        self.assertContains(response, 'aria-label="First Name sheet column"')
        self.assertFalse(RegistrationSheetSyncConfig.objects.filter(event=self.event).exists())
        self.inspect.assert_not_called()
        self.sync.assert_not_called()
        self.create.assert_not_called()
        self.scheduler.assert_not_called()

    def test_saves_connection_timing_labels_and_column_mapping(self):
        response = self.client.post(
            self.url,
            self.settings_data(
                spreadsheet="https://docs.google.com/spreadsheets/d/other-sheet/edit#gid=42",
                worksheet_id="",
                sync_mode="interval",
                interval_minutes="15",
                header_row="3",
                field_0_label="Given name",
                field_0_column="B",
            ),
        )
        self.assertRedirects(response, self.url)
        self.event.refresh_from_db()
        config = RegistrationSheetSyncConfig.objects.get(event=self.event)
        self.assertEqual(self.event.registration_sheet_id, "other-sheet")
        self.assertEqual(self.event.registration_sheet_gid, 42)
        self.assertEqual((config.sync_mode, config.interval_minutes, config.header_row), ("interval", 15, 3))
        self.assertEqual(config.field_settings["first_name"], {"enabled": True, "label": "Given name"})
        self.assertEqual(config.column_mappings, {"first_name": 2})
        self.assertEqual((config.debounce_seconds, config.max_delay_seconds), (15, 60))
        self.scheduler.assert_called_once()
        self.inspect.assert_not_called()
        self.sync.assert_not_called()

    def test_can_save_settings_without_a_sheet_connection(self):
        response = self.client.post(self.url, self.settings_data(spreadsheet="", worksheet_id=""))
        self.assertRedirects(response, self.url)
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_id, "")
        self.assertIsNone(self.event.registration_sheet_gid)

    def test_required_identity_fields_cannot_be_disabled(self):
        data = self.settings_data()
        del data["field_2_enabled"]
        del data["field_3_enabled"]
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url)
        config = RegistrationSheetSyncConfig.objects.get(event=self.event)
        self.assertTrue(config.field_settings["registration_id"]["enabled"])
        self.assertTrue(config.field_settings["status"]["enabled"])

    def test_preserves_settings_for_temporarily_removed_questions(self):
        self.config(field_settings={"question:removed": {"enabled": False, "label": "Old question"}})
        self.client.post(self.url, self.settings_data())
        config = RegistrationSheetSyncConfig.objects.get(event=self.event)
        self.assertEqual(config.field_settings["question:removed"], {"enabled": False, "label": "Old question"})
