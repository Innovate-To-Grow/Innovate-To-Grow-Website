from django.test import TestCase

from core.admin.maintenance import SiteMaintenanceControlAdminForm
from core.models import SiteMaintenanceControl


class SiteMaintenanceControlAdminFormTests(TestCase):
    def test_password_field_is_not_prefilled(self):
        config = SiteMaintenanceControl.objects.create(is_maintenance=True, bypass_password="secret123")

        form = SiteMaintenanceControlAdminForm(instance=config)

        self.assertEqual(form.fields["bypass_password"].initial, "")
        self.assertFalse(form.fields["bypass_password"].widget.render_value)

    def test_blank_password_keeps_existing_hash_without_clear_flag(self):
        config = SiteMaintenanceControl.objects.create(is_maintenance=True, bypass_password="secret123")
        original_hash = config.bypass_password

        form = SiteMaintenanceControlAdminForm(
            data={
                "is_maintenance": True,
                "message": config.message,
                "bypass_password": "",
                "clear_bypass_password": False,
            },
            instance=config,
        )

        self.assertTrue(form.is_valid())
        updated = form.save()
        self.assertEqual(updated.bypass_password, original_hash)

    def test_clear_flag_removes_existing_bypass_password(self):
        config = SiteMaintenanceControl.objects.create(is_maintenance=True, bypass_password="secret123")

        form = SiteMaintenanceControlAdminForm(
            data={
                "is_maintenance": True,
                "message": config.message,
                "bypass_password": "",
                "clear_bypass_password": True,
            },
            instance=config,
        )

        self.assertTrue(form.is_valid())
        updated = form.save()
        self.assertEqual(updated.bypass_password, "")
