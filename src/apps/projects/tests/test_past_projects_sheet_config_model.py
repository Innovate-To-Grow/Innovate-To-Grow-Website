from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import PastProjectsSheetConfig


class PastProjectsSheetConfigModelTest(TestCase):
    def test_str_configured(self):
        config = PastProjectsSheetConfig.objects.create(name="Production")
        self.assertEqual(str(config), "Production")

    def test_str_not_configured(self):
        config = PastProjectsSheetConfig.objects.create(name="")
        self.assertEqual(str(config), "Not configured")

    def test_single_active_invariant(self):
        first = PastProjectsSheetConfig.objects.create(name="First", is_active=True)
        second = PastProjectsSheetConfig.objects.create(name="Second", is_active=True)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(PastProjectsSheetConfig.load(), second)

    def test_load_returns_none_when_no_active(self):
        PastProjectsSheetConfig.objects.create(name="Inactive", is_active=False)
        self.assertIsNone(PastProjectsSheetConfig.load())

    def test_load_returns_active(self):
        active = PastProjectsSheetConfig.objects.create(name="Active", is_active=True)
        self.assertEqual(PastProjectsSheetConfig.load(), active)

    def test_sync_is_due_disabled_false(self):
        config = PastProjectsSheetConfig(auto_sync_enabled=False)
        self.assertFalse(config.sync_is_due)

    def test_sync_is_due_never_synced_true(self):
        config = PastProjectsSheetConfig(auto_sync_enabled=True, last_synced_at=None)
        self.assertTrue(config.sync_is_due)

    def test_sync_is_due_recent_false(self):
        config = PastProjectsSheetConfig(
            auto_sync_enabled=True,
            sync_interval_minutes=1440,
            last_synced_at=timezone.now(),
        )
        self.assertFalse(config.sync_is_due)

    def test_sync_is_due_elapsed_true(self):
        config = PastProjectsSheetConfig(
            auto_sync_enabled=True,
            sync_interval_minutes=60,
            last_synced_at=timezone.now() - timedelta(minutes=61),
        )
        self.assertTrue(config.sync_is_due)

    def test_deactivating_does_not_touch_others(self):
        active = PastProjectsSheetConfig.objects.create(name="Active", is_active=True)
        inactive = PastProjectsSheetConfig.objects.create(name="Inactive", is_active=False)

        # Re-saving an inactive row must not flip the active one off.
        inactive.name = "Inactive renamed"
        inactive.save()

        active.refresh_from_db()
        self.assertTrue(active.is_active)
