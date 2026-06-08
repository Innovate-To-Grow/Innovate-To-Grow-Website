"""Per-app admin access for the event app's permission overrides.

The event app re-enables delete on two ReadOnlyModelAdmin subclasses
(sync log + check-in record) and add/delete on the registration admin. Each
override must be scoped to the ``event`` app grant (see
apps.core.access.user_can_access_app), not a bare ``is_staff``/``True`` bypass:
event-granted staff are allowed, other-app staff are denied, superusers bypass.
"""

from django.test import RequestFactory, TestCase

from apps.event.admin.checkin import CheckInRecordAdmin
from apps.event.admin.registration import EventRegistrationAdmin
from apps.event.admin.sync_log import RegistrationSheetSyncLogAdmin
from apps.event.models import CheckInRecord, EventRegistration, RegistrationSheetSyncLog
from apps.event.tests.helpers import make_admin, make_superuser


class EventAdminPerAppPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event_staff = make_admin(apps=["event"], email="event-admin@example.com")
        cls.other_staff = make_admin(apps=["cms"], email="cms-only-admin@example.com")
        cls.superuser = make_superuser(email="master-perms@example.com")

    def _request(self, user):
        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def _assert_delete_scoped(self, admin_instance):
        self.assertTrue(admin_instance.has_delete_permission(self._request(self.event_staff)))
        self.assertFalse(admin_instance.has_delete_permission(self._request(self.other_staff)))
        self.assertTrue(admin_instance.has_delete_permission(self._request(self.superuser)))

    def test_sync_log_delete_is_event_app_scoped(self):
        admin_instance = RegistrationSheetSyncLogAdmin(RegistrationSheetSyncLog, None)
        self._assert_delete_scoped(admin_instance)

    def test_checkin_record_delete_is_event_app_scoped(self):
        admin_instance = CheckInRecordAdmin(CheckInRecord, None)
        self._assert_delete_scoped(admin_instance)

    def test_registration_add_is_event_app_scoped(self):
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self.assertTrue(admin_instance.has_add_permission(self._request(self.event_staff)))
        self.assertFalse(admin_instance.has_add_permission(self._request(self.other_staff)))
        self.assertTrue(admin_instance.has_add_permission(self._request(self.superuser)))

    def test_registration_delete_is_event_app_scoped(self):
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self._assert_delete_scoped(admin_instance)


class EventAdminPerAppChangelistAccessTest(TestCase):
    """Drive the event changelist through the full admin request stack."""

    EVENT_URL = "/admin/event/event/"
    NON_EVENT_URL = "/admin/cms/cmspage/"

    def test_event_granted_staff_can_open_event_changelist(self):
        user = make_admin(apps=["event"], email="event-changelist@example.com")
        self.client.force_login(user)

        self.assertEqual(self.client.get(self.EVENT_URL).status_code, 200)
        self.assertEqual(self.client.get(self.NON_EVENT_URL).status_code, 403)

    def test_superuser_can_open_event_changelist(self):
        user = make_superuser(email="master-changelist@example.com")
        self.client.force_login(user)

        self.assertEqual(self.client.get(self.EVENT_URL).status_code, 200)
