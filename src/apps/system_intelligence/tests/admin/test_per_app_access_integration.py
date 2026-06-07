"""End-to-end per-app admin access for system_intelligence via the test client.

Drives a real system_intelligence admin URL through the full request stack to
confirm BaseModelAdmin's per-app gate: a staff member granted the
``system_intelligence`` app loads the changelist, a staff member granted only a
different app is forbidden, and a superuser (I2G Master) is always allowed.
"""

from django.test import TestCase

from apps.event.tests.helpers import make_admin, make_superuser

SI_CONFIG_URL = "/admin/system_intelligence/systemintelligenceconfig/"


class SystemIntelligencePerAppAdminAccessTest(TestCase):
    def test_system_intelligence_staff_can_access(self):
        user = make_admin(apps=["system_intelligence"], email="si-admin@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get(SI_CONFIG_URL).status_code, 200)

    def test_other_app_staff_is_forbidden(self):
        user = make_admin(apps=["cms"], email="cms-only-admin@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get(SI_CONFIG_URL).status_code, 403)

    def test_superuser_can_access(self):
        user = make_superuser(email="si-master@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get(SI_CONFIG_URL).status_code, 200)
