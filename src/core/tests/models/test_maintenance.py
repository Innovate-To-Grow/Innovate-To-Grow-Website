"""Tests for the SiteMaintenanceControl singleton model."""

from django.test import TestCase

from core.models import SiteMaintenanceControl


class SiteMaintenanceControlModelTest(TestCase):
    def test_load_creates_singleton(self):
        config = SiteMaintenanceControl.load()
        self.assertEqual(config.pk, 1)
        self.assertFalse(config.is_maintenance)

    def test_load_returns_existing(self):
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=True, message="Down")
        config = SiteMaintenanceControl.load()

        self.assertTrue(config.is_maintenance)
        self.assertEqual(config.message, "Down")

    def test_save_enforces_pk_one(self):
        obj = SiteMaintenanceControl(pk=42, is_maintenance=True)
        obj.save()

        self.assertEqual(obj.pk, 1)
        self.assertEqual(SiteMaintenanceControl.objects.count(), 1)

    def test_str_on(self):
        config = SiteMaintenanceControl(is_maintenance=True)
        self.assertEqual(str(config), "Maintenance Mode: ON")

    def test_str_off(self):
        config = SiteMaintenanceControl(is_maintenance=False)
        self.assertEqual(str(config), "Maintenance Mode: OFF")
