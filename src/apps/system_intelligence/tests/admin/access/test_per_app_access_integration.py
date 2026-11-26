"""End-to-end admin access for system_intelligence via the test client.

Drives a real system_intelligence admin URL through the full request stack: every Admin loads the changelist, and a
signed-in regular member is sent to the admin login.
"""

from django.test import TestCase

from apps.event.tests.helpers import make_admin, make_member

SI_CONFIG_URL = "/admin/system_intelligence/systemintelligenceconfig/"


class SystemIntelligenceAdminAccessTest(TestCase):
    def test_every_admin_can_access(self):
        user = make_admin(email="si-admin@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get(SI_CONFIG_URL).status_code, 200)

    def test_a_regular_member_is_sent_to_the_login(self):
        user = make_member(email="si-member@example.com")
        self.client.force_login(user)
        response = self.client.get(SI_CONFIG_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
