from django.urls import reverse
from rest_framework.test import APIClient

from apps.event.admin.registration_sheet.form import RegistrationSheetSyncForm
from apps.event.models import RegistrationSheetSyncConfig
from apps.event.services import registration_sheet_sync as sync_api
from apps.event.tests.admin.sheet_sync.test_registration_sheet_sync_admin import _RegistrationSheetSyncAdminCase
from apps.event.tests.helpers import make_admin


class RegistrationSheetSyncAdminTest(_RegistrationSheetSyncAdminCase):
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
