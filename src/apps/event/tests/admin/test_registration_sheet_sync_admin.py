import copy
from unittest.mock import patch

from django.core import signing
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.event.admin.registration.sheet_sync import REVIEW_SALT, RegistrationSheetSyncForm
from apps.event.models import RegistrationSheetSyncConfig
from apps.event.services import registration_sheet_sync as sync_api
from apps.event.tests.helpers import make_admin, make_event, make_superuser

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


class RegistrationSheetSyncAdminTest(TestCase):
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

    def test_invalid_mappings_labels_headers_modes_and_urls_do_not_save(self):
        cases = [
            ({"field_0_column": "A", "field_1_column": "1"}, "only one field"),
            ({"field_0_column": "ZZZZ"}, "column letter"),
            ({"field_0_column": "0"}, "A to ZZZ"),
            ({"field_0_label": "Registration ID"}, "different column labels"),
            ({"header_row": "1001"}, "less than or equal to 1000"),
            ({"sync_mode": "forever"}, "Select a valid choice"),
            ({"interval_minutes": "2"}, "Select a valid choice"),
            ({"spreadsheet": "https://example.com/spreadsheets/d/example"}, "Google Sheets URL"),
        ]
        for values, text in cases:
            with self.subTest(values=values):
                response = self.client.post(self.url, self.settings_data(**values))
                self.assertContains(response, text, status_code=400)
        self.assertFalse(RegistrationSheetSyncConfig.objects.filter(event=self.event).exists())
        self.scheduler.assert_not_called()
        self.inspect.assert_not_called()

    def test_corrected_settings_resume_blocked_sync_but_unchanged_settings_do_not(self):
        config = self.config(sync_mode="manual", state="blocked", last_error="Resolve duplicate mapping.")
        response = self.client.post(self.url, self.settings_data())
        self.assertRedirects(response, self.url)
        config.refresh_from_db()
        self.assertEqual(config.state, "blocked")
        response = self.client.post(self.url, self.settings_data(header_row="2"))
        self.assertRedirects(response, self.url)
        config.refresh_from_db()
        self.assertEqual(config.state, "idle")
        self.assertEqual(config.last_error, "")

    def test_long_question_labels_can_be_saved(self):
        self.schema_patch.stop()
        long_fields = [{**FIELDS[0], "label": "Question " + "x" * 400}, *FIELDS[1:]]
        with patch.object(sync_api, "available_registration_fields", return_value=long_fields, create=True):
            data = self.settings_data(field_0_label=long_fields[0]["label"])
            response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def test_preview_and_check_use_unsaved_draft_without_writing_or_scheduling(self):
        self.config(sync_mode="manual")
        for action in ("preview", "check_connection"):
            with self.subTest(action=action):
                response = self.client.post(
                    self.url,
                    self.settings_data(action=action, spreadsheet="draft-sheet", header_row="4", field_0_column="C"),
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "No spreadsheet data or saved settings were changed.")
                args, kwargs = self.inspect.call_args
                self.assertEqual(args[0].registration_sheet_id, "draft-sheet")
                self.assertEqual(kwargs["config"].header_row, 4)
                self.assertEqual(kwargs["config"].column_mappings, {"first_name": 3})
        self.event.refresh_from_db()
        self.assertEqual(self.event.registration_sheet_id, "test-sheet")
        self.assertEqual(RegistrationSheetSyncConfig.objects.get(event=self.event).header_row, 1)
        self.scheduler.assert_not_called()
        self.sync.assert_not_called()
        self.create.assert_not_called()

    def test_sync_now_only_enqueues_an_immediate_job(self):
        response = self.client.post(self.url, {"action": "sync_now"})
        self.assertRedirects(response, self.url)
        self.scheduler.assert_called_once_with(self.event, immediate=True)
        self.sync.assert_not_called()
        self.inspect.assert_not_called()
        self.create.assert_not_called()

    def test_missing_connection_cannot_sync_or_create(self):
        self.event.registration_sheet_id = ""
        self.event.save(update_fields=["registration_sheet_id"])
        self.scheduler.reset_mock()
        for action in ("sync_now", "review_create", "review_rebuild", "review_adoption"):
            with self.subTest(action=action):
                response = self.client.post(self.url, {"action": action})
                self.assertContains(response, "Save a spreadsheet connection", status_code=400)
        self.scheduler.assert_not_called()
        self.create.assert_not_called()
        self.inspect.assert_not_called()

    def test_adoption_requires_review_and_backup_confirmation(self):
        token = self.review_token("adoption")
        self.sync.assert_not_called()
        response = self.client.post(self.url, {"action": "confirm_adoption", "review_token": token})
        self.assertContains(response, "Confirm that a backup", status_code=400)
        self.sync.assert_not_called()
        response = self.client.post(
            self.url, {"action": "confirm_adoption", "review_token": token, "backup_acknowledged": "on"}
        )
        self.assertRedirects(response, self.url)
        self.sync.assert_called_once_with(self.event, adopt_legacy=True, expected_fingerprint="sheet-snapshot-1")

    def test_create_and_rebuild_require_bound_review_before_engine_write(self):
        for operation in ("create", "rebuild"):
            with self.subTest(operation=operation):
                self.create.reset_mock()
                response = self.client.post(self.url, {"action": f"confirm_{operation}", "backup_acknowledged": "on"})
                self.assertContains(response, "review is missing or expired", status_code=400)
                self.create.assert_not_called()
                token = self.review_token(operation)
                self.create.assert_not_called()
                response = self.client.post(
                    self.url, {"action": f"confirm_{operation}", "review_token": token, "backup_acknowledged": "on"}
                )
                self.assertRedirects(response, self.url)
                self.create.assert_called_once_with(self.event, expected_fingerprint="sheet-snapshot-1")

    def test_changed_configuration_invalidates_review(self):
        token = self.review_token("rebuild")
        self.config(header_row=2)
        response = self.client.post(
            self.url, {"action": "confirm_rebuild", "review_token": token, "backup_acknowledged": "on"}
        )
        self.assertContains(response, "saved settings or review have changed", status_code=400)
        self.create.assert_not_called()

    def test_cross_user_and_wrong_operation_reviews_are_rejected(self):
        token = self.review_token("create")
        response = self.client.post(
            self.url, {"action": "confirm_rebuild", "review_token": token, "backup_acknowledged": "on"}
        )
        self.assertEqual(response.status_code, 400)
        self.client.force_login(make_superuser(email="second-admin@example.com"))
        response = self.client.post(
            self.url, {"action": "confirm_create", "review_token": token, "backup_acknowledged": "on"}
        )
        self.assertEqual(response.status_code, 400)
        self.create.assert_not_called()

    def test_expired_review_cannot_be_replayed(self):
        token = self.review_token("create")
        payload = signing.loads(token, salt=REVIEW_SALT)
        signer = signing.TimestampSigner(salt=REVIEW_SALT)
        with patch.object(signer, "timestamp", return_value="0"):
            expired_token = signer.sign_object(payload)
        response = self.client.post(
            self.url, {"action": "confirm_create", "review_token": expired_token, "backup_acknowledged": "on"}
        )
        self.assertContains(response, "review is missing or expired", status_code=400)
        self.create.assert_not_called()

    def test_conflicting_legacy_rows_cannot_be_adopted(self):
        self.inspect.return_value = {
            **copy.deepcopy(PREVIEW),
            "requires_adoption": True,
            "conflicts": ["Duplicate ticket code"],
        }
        response = self.client.post(self.url, {"action": "review_adoption"})
        self.assertContains(response, "unambiguous match preview", status_code=400)
        self.sync.assert_not_called()

    def test_changed_sheet_is_reported_without_claiming_success(self):
        token = self.review_token("adoption")
        self.sync.side_effect = sync_api.RegistrationSyncError("The sheet changed. Preview again.")
        response = self.client.post(
            self.url, {"action": "confirm_adoption", "review_token": token, "backup_acknowledged": "on"}
        )
        self.assertContains(response, "The sheet changed. Preview again.", status_code=400)

    def test_connection_error_is_readable_and_never_saves_draft(self):
        self.inspect.side_effect = sync_api.RegistrationSyncError("The service account cannot access this spreadsheet.")
        response = self.client.post(self.url, self.settings_data(action="check_connection"))
        self.assertContains(response, "cannot access this spreadsheet", status_code=400)
        self.scheduler.assert_not_called()
        self.assertFalse(RegistrationSheetSyncConfig.objects.filter(event=self.event).exists())

    def test_per_app_permissions_and_csrf_are_enforced(self):
        outsider = make_admin(apps=["cms"], email="cms-admin@example.com")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"action": "sync_now"}).status_code, 403)
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {"action": "sync_now"}).status_code, 403)
        self.scheduler.assert_not_called()

    def test_unknown_action_and_unsupported_method_are_rejected(self):
        self.assertEqual(self.client.post(self.url, {"action": "clear_sheet"}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {}).status_code, 400)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        self.create.assert_not_called()
        self.sync.assert_not_called()

    def test_event_and_registration_navigation_link_to_manager(self):
        response = self.client.get(reverse("admin:event_event_change", args=[self.event.pk]))
        self.assertContains(response, self.url)
        self.assertContains(response, "Manage sync")
        response = self.client.get(reverse("admin:event_eventregistration_changelist"))
        self.assertContains(response, self.url)
        self.assertContains(response, "Manage sheet sync")

    def test_form_column_letter_and_numeric_values_are_equivalent(self):
        config = RegistrationSheetSyncConfig(event=self.event)
        form = RegistrationSheetSyncForm(
            self.settings_data(field_0_column="AA", field_1_column="28"), event=self.event, config=config
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["column_mappings"], {"first_name": 27, "organization": 28})
