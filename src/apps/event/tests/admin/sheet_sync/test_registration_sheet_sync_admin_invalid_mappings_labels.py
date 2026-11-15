import copy
from unittest.mock import patch

from django.core import signing

from apps.event.admin.registration_sheet.review import REVIEW_SALT
from apps.event.models import RegistrationSheetSyncConfig
from apps.event.services import registration_sheet_sync as sync_api
from apps.event.tests.admin.sheet_sync.test_registration_sheet_sync_admin import (
    FIELDS,
    PREVIEW,
    _RegistrationSheetSyncAdminCase,
)
from apps.event.tests.helpers import make_superuser


class RegistrationSheetSyncAdminTest(_RegistrationSheetSyncAdminCase):
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
