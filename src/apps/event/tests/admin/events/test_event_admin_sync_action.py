from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from apps.event.admin.event import EventAdmin
from apps.event.models import Event
from apps.event.services.registration_sheet_sync import RegistrationSyncError
from apps.event.tests.helpers import make_event, make_superuser


class EventAdminSyncActionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = make_superuser(email="sync-action-admin@example.com")
        self.admin = EventAdmin(Event, AdminSite())
        self.event = make_event(name="Sync Action Event")

    def _request(self):
        request = self.factory.post("/admin/")
        request.user = self.user
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    @patch("apps.event.services.registration_sheet_sync.sync_registrations_to_sheet", return_value=7)
    def test_action_reports_success(self, mock_sync):
        request = self._request()
        self.admin.sync_registrations_to_sheet(request, Event.objects.filter(pk=self.event.pk))

        mock_sync.assert_called_once()
        messages = [str(m) for m in request._messages]
        self.assertTrue(any("Synced 7 registrations" in m for m in messages))

    @patch(
        "apps.event.services.registration_sheet_sync.sync_registrations_to_sheet",
        side_effect=RegistrationSyncError("not configured"),
    )
    def test_action_reports_failure(self, mock_sync):
        request = self._request()
        self.admin.sync_registrations_to_sheet(request, Event.objects.filter(pk=self.event.pk))

        messages = [str(m) for m in request._messages]
        self.assertTrue(any("Sync failed" in m and "not configured" in m for m in messages))
