from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.event.admin.schedule_sync_log import ScheduleSyncLogAdmin
from apps.event.admin.sync_log import RegistrationSheetSyncLogAdmin
from apps.event.models import RegistrationSheetSyncLog, ScheduleSyncLog
from apps.event.tests.helpers import make_member, make_superuser


class ScheduleSyncLogAdminTest(TestCase):
    def setUp(self):
        self.admin = ScheduleSyncLogAdmin(ScheduleSyncLog, AdminSite())

    def test_sync_type_badge_auto(self):
        log = ScheduleSyncLog(sync_type=ScheduleSyncLog.SyncType.AUTO)
        self.assertEqual(self.admin.sync_type_badge(log), ("Auto", "info"))

    def test_sync_type_badge_manual(self):
        log = ScheduleSyncLog(sync_type=ScheduleSyncLog.SyncType.MANUAL)
        self.assertEqual(self.admin.sync_type_badge(log), ("Manual", "warning"))

    def test_status_badge_success(self):
        log = ScheduleSyncLog(status=ScheduleSyncLog.Status.SUCCESS)
        self.assertEqual(self.admin.status_badge(log), ("Success", "success"))

    def test_status_badge_failed(self):
        log = ScheduleSyncLog(status=ScheduleSyncLog.Status.FAILED)
        self.assertEqual(self.admin.status_badge(log), ("Failed", "danger"))

    def test_error_short_empty(self):
        self.assertEqual(self.admin.error_short(ScheduleSyncLog(error_message="")), "-")

    def test_error_short_truncates(self):
        log = ScheduleSyncLog(error_message="z" * 200)
        self.assertEqual(self.admin.error_short(log), "z" * 80 + "...")

    def test_error_short_keeps_short(self):
        self.assertEqual(self.admin.error_short(ScheduleSyncLog(error_message="oops")), "oops")


class RegistrationSheetSyncLogAdminTest(TestCase):
    def setUp(self):
        self.admin = RegistrationSheetSyncLogAdmin(RegistrationSheetSyncLog, AdminSite())
        self.factory = RequestFactory()

    def test_sync_type_badge_full(self):
        log = RegistrationSheetSyncLog(sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        self.assertEqual(self.admin.sync_type_badge(log), ("Full Sync", "warning"))

    def test_sync_type_badge_append(self):
        log = RegistrationSheetSyncLog(sync_type=RegistrationSheetSyncLog.SyncType.APPEND)
        self.assertEqual(self.admin.sync_type_badge(log), ("Append", "info"))

    def test_status_badge_success(self):
        log = RegistrationSheetSyncLog(status=RegistrationSheetSyncLog.Status.SUCCESS)
        self.assertEqual(self.admin.status_badge(log), ("Success", "success"))

    def test_status_badge_failed(self):
        log = RegistrationSheetSyncLog(status=RegistrationSheetSyncLog.Status.FAILED)
        self.assertEqual(self.admin.status_badge(log), ("Failed", "danger"))

    def test_error_short_empty(self):
        self.assertEqual(self.admin.error_short(RegistrationSheetSyncLog(error_message="")), "-")

    def test_error_short_truncates(self):
        log = RegistrationSheetSyncLog(error_message="z" * 200)
        self.assertEqual(self.admin.error_short(log), "z" * 80 + "...")

    def test_error_short_keeps_short(self):
        self.assertEqual(self.admin.error_short(RegistrationSheetSyncLog(error_message="boom")), "boom")

    def test_delete_permission_requires_staff(self):
        request = self.factory.get("/admin/")
        request.user = make_superuser(email="syncdel-admin@example.com")
        self.assertTrue(self.admin.has_delete_permission(request))

        request.user = make_member(email="nonstaff-sync@example.com")
        self.assertFalse(self.admin.has_delete_permission(request))
