import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from apps.event.models import CurrentProjectSchedule

disable_auto_sync_on_inactive_schedules = importlib.import_module(
    "apps.event.migrations.0011_currentprojectschedule_auto_sync_help_text"
).disable_auto_sync_on_inactive_schedules


class AutoSyncResetMigrationTest(TestCase):
    def test_only_inactive_rows_lose_the_auto_sync_flag(self):
        # Bypass the model's own activation rule so the fixture mirrors legacy
        # data: an archived row that still carries auto_sync_enabled=True.
        active = CurrentProjectSchedule.objects.create(name="2026", auto_sync_enabled=True)
        archived = CurrentProjectSchedule.objects.create(name="2025", is_active=False)
        CurrentProjectSchedule.objects.filter(pk=archived.pk).update(auto_sync_enabled=True)
        untouched = CurrentProjectSchedule.objects.create(name="2024", is_active=False, auto_sync_enabled=False)

        disable_auto_sync_on_inactive_schedules(django_apps, None)

        active.refresh_from_db()
        archived.refresh_from_db()
        untouched.refresh_from_db()
        self.assertTrue(active.auto_sync_enabled)
        self.assertFalse(archived.auto_sync_enabled)
        self.assertFalse(untouched.auto_sync_enabled)
