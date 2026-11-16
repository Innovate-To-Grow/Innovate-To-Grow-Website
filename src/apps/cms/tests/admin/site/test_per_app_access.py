"""Integration tests for per-Django-app admin access on the cms app.

These exercise the gate end-to-end through the Django admin test client:
a cms-granted staff member may reach cms changelists but not other apps';
superusers (I2G Master) may reach everything.
"""

from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser


class CMSAdminPerAppAccessTests(TestCase):
    def setUp(self):
        self.cms_changelist = reverse("admin:cms_cmspage_changelist")
        self.event_changelist = reverse("admin:event_event_changelist")

    def test_cms_staff_can_view_cms_changelist(self):
        user = make_admin(apps=["cms"], email="cms-access@example.com")
        self.client.force_login(user)
        resp = self.client.get(self.cms_changelist)
        self.assertEqual(resp.status_code, 200)

    def test_cms_staff_denied_non_cms_changelist(self):
        user = make_admin(apps=["cms"], email="cms-only@example.com")
        self.client.force_login(user)
        resp = self.client.get(self.event_changelist)
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_view_cms_changelist(self):
        user = make_superuser(email="master-access@example.com")
        self.client.force_login(user)
        resp = self.client.get(self.cms_changelist)
        self.assertEqual(resp.status_code, 200)

    def test_superuser_can_view_non_cms_changelist(self):
        user = make_superuser(email="master-cross@example.com")
        self.client.force_login(user)
        resp = self.client.get(self.event_changelist)
        self.assertEqual(resp.status_code, 200)

    def test_other_app_staff_denied_cms_changelist(self):
        user = make_admin(apps=["event"], email="event-access@example.com")
        self.client.force_login(user)
        resp = self.client.get(self.cms_changelist)
        self.assertEqual(resp.status_code, 403)
