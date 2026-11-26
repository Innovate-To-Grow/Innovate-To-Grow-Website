from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse
from rest_framework.test import APIClient

from apps.event.admin.registration_sheet.form import RegistrationSheetSyncForm
from apps.event.models import Event, RegistrationSheetSyncConfig
from apps.event.services import registration_sheet_sync as sync_api
from apps.event.tests.admin.sheet_sync.test_registration_sheet_sync_admin import _RegistrationSheetSyncAdminCase
from apps.event.tests.helpers import make_member


class RegistrationSheetSyncAdminTest(_RegistrationSheetSyncAdminCase):
    def test_connection_error_is_readable_and_never_saves_draft(self):
        self.inspect.side_effect = sync_api.RegistrationSyncError("The service account cannot access this spreadsheet.")
        response = self.client.post(self.url, self.settings_data(action="check_connection"))
        self.assertContains(response, "cannot access this spreadsheet", status_code=400)
        self.scheduler.assert_not_called()
        self.assertFalse(RegistrationSheetSyncConfig.objects.filter(event=self.event).exists())

    def test_admin_access_and_csrf_are_enforced(self):
        outsider = make_member(email="plain-sheet@example.com")
        self.client.force_login(outsider)
        for response in (self.client.get(self.url), self.client.post(self.url, {"action": "sync_now"})):
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response["Location"])
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {"action": "sync_now"}).status_code, 403)
        self.scheduler.assert_not_called()

    def test_the_view_rechecks_the_admin_permission_hooks_when_called_directly(self):
        event_admin = admin.site._registry[Event]
        request = RequestFactory().get(self.url)
        request.user = make_member(email="direct-sheet@example.com")
        with self.assertRaises(PermissionDenied):
            event_admin.registration_sheet_sync_view(request, self.event.pk)

        request = RequestFactory().post(self.url, {"action": "sync_now"})
        request.user = self.user
        with patch.object(type(event_admin), "has_change_permission", return_value=False):
            with self.assertRaises(PermissionDenied):
                event_admin.registration_sheet_sync_view(request, self.event.pk)
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
