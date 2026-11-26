"""Who may use the cms admin: every Admin reaches the cms changelists (and every other app's); a regular member is sent
to the admin login."""

from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_member


class CMSAdminAccessTests(TestCase):
    def setUp(self):
        self.cms_changelist = reverse("admin:cms_cmspage_changelist")
        self.event_changelist = reverse("admin:event_event_changelist")

    def test_an_admin_can_view_the_cms_and_other_changelists(self):
        self.client.force_login(make_admin(email="cms-access@example.com"))

        self.assertEqual(self.client.get(self.cms_changelist).status_code, 200)
        self.assertEqual(self.client.get(self.event_changelist).status_code, 200)

    def test_a_regular_member_is_sent_to_the_admin_login(self):
        self.client.force_login(make_member(email="cms-member@example.com"))

        response = self.client.get(self.cms_changelist)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
