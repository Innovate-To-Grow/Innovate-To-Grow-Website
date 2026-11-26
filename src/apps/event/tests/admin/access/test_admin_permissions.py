"""Admin access for the event app's permission overrides.

The event app re-enables delete on two ReadOnlyModelAdmin subclasses (sync log + check-in record) and add/delete on the
registration admin. Each override follows the Admin rule (apps.core.utils.access.user_can_access_app), not a bare
``True``: every Admin is allowed, a regular member is denied.
"""

from django.test import RequestFactory, TestCase

from apps.event.admin.registration import EventRegistrationAdmin
from apps.event.admin.registration.checkin import CheckInRecordAdmin
from apps.event.admin.registration_sheet.sync_log import RegistrationSheetSyncLogAdmin
from apps.event.models import CheckInRecord, EventRegistration, RegistrationSheetSyncLog
from apps.event.tests.helpers import make_admin, make_member


class EventAdminPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = make_admin(email="event-admin@example.com")
        cls.member = make_member(email="plain-perms@example.com")

    def _request(self, user):
        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def _assert_delete_for_admins_only(self, admin_instance):
        self.assertTrue(admin_instance.has_delete_permission(self._request(self.admin_user)))
        self.assertFalse(admin_instance.has_delete_permission(self._request(self.member)))

    def test_sync_log_delete_is_for_admins_only(self):
        self._assert_delete_for_admins_only(RegistrationSheetSyncLogAdmin(RegistrationSheetSyncLog, None))

    def test_checkin_record_delete_is_for_admins_only(self):
        self._assert_delete_for_admins_only(CheckInRecordAdmin(CheckInRecord, None))

    def test_registration_add_is_for_admins_only(self):
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self.assertTrue(admin_instance.has_add_permission(self._request(self.admin_user)))
        self.assertFalse(admin_instance.has_add_permission(self._request(self.member)))

    def test_registration_delete_is_for_admins_only(self):
        self._assert_delete_for_admins_only(EventRegistrationAdmin(EventRegistration, None))


class EventAdminChangelistAccessTest(TestCase):
    """Drive the event changelist through the full admin request stack."""

    EVENT_URL = "/admin/event/event/"
    NON_EVENT_URL = "/admin/cms/cmspage/"

    def test_an_admin_can_open_the_event_and_every_other_changelist(self):
        self.client.force_login(make_admin(email="event-changelist@example.com"))

        self.assertEqual(self.client.get(self.EVENT_URL).status_code, 200)
        self.assertEqual(self.client.get(self.NON_EVENT_URL).status_code, 200)

    def test_a_regular_member_is_sent_to_the_admin_login(self):
        self.client.force_login(make_member(email="plain-changelist@example.com"))

        response = self.client.get(self.EVENT_URL)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
