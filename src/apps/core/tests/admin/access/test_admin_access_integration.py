"""End-to-end admin access via the Django admin test client.

Drives real admin URLs through the full request stack to confirm BaseModelAdmin's rule: every Admin (an active staff
member) reaches every app's models, and a signed-in member who is not an Admin is sent to the admin sign-in.
"""

from django.test import TestCase

from apps.event.tests.helpers import make_admin, make_member

URLS = (
    "/admin/",
    "/admin/cms/cmspage/",
    "/admin/event/event/",
    "/admin/projects/project/",
    "/admin/core/backgroundjob/",
)


class AdminAccessIntegrationTest(TestCase):
    def test_every_admin_reaches_every_app(self):
        self.client.force_login(make_admin(email="admin@example.com"))
        for url in URLS:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_a_member_who_is_not_an_admin_is_sent_to_the_sign_in(self):
        self.client.force_login(make_member(email="member@example.com"))
        for url in URLS:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])

    def test_an_inactive_admin_is_sent_to_the_sign_in(self):
        member = make_admin(email="gone@example.com")
        self.client.force_login(member)
        member.is_active = False
        member.save(update_fields=["is_active"])
        response = self.client.get("/admin/cms/cmspage/")
        self.assertEqual(response.status_code, 302)
