"""Who may open the ContactPhone normalize URLs.

The two custom admin URLs on ``ContactPhoneAdmin`` (``_normalize_preview_view`` and ``_normalize_apply_view``) are
registered via ``self.admin_site.admin_view(...)``, which admits active Admins only: the preview shows member phone
PII and the apply step rewrites phone records. A signed-in member who is not an Admin is sent to the admin login.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import Member
from apps.authn.tests.admin.members.security.admins.fixtures import make_admin_member


class ContactPhoneNormalizeAccessTest(TestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(password="StrongPass123!", is_active=True)
        self.admin = make_admin_member(first_name="Ada", last_name="Admin")
        self.preview_url = reverse("admin:authn_contactphone_normalize_preview")
        self.apply_url = reverse("admin:authn_contactphone_normalize_apply")

    def tearDown(self):
        cache.clear()

    def test_a_member_who_is_not_an_admin_is_sent_to_the_admin_login(self):
        self.client.force_login(self.member)
        for response in (
            self.client.get(self.preview_url),
            self.client.get(self.apply_url),
            self.client.post(self.apply_url, {}),
        ):
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("admin:login"), response["Location"])

    def test_an_admin_can_preview(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.preview_url).status_code, 200)

    def test_a_get_on_apply_returns_to_the_preview(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.apply_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.preview_url)
