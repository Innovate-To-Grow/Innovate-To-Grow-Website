"""Impersonation never targets an Admin account; the member tooling URLs admit Admins only.

``Login as Member`` is an end-user support tool, so no Admin (whoever they are) can mint a login token for another
Admin, or for themselves. The export / import / template / review URLs hold member PII: ``admin_site.admin_view``
sends a signed-in member who is not an Admin to the admin login.
"""

from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ImpersonationToken, Member, MemberImportBatch
from apps.authn.tests.admin.members.security.admins.fixtures import PASSWORD, AdminPeersCase


class ImpersonationTests(AdminPeersCase):
    def _url(self, target):
        return reverse("admin:authn_member_impersonate", args=[target.pk])

    def test_an_admin_can_impersonate_a_regular_member(self):
        response = self.client.post(self._url(self.regular))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/impersonate-login#token=", response["Location"])
        self.assertTrue(ImpersonationToken.objects.filter(member=self.regular).exists())

    def test_no_admin_account_is_impersonated(self):
        superuser = Member.objects.create_superuser(password=PASSWORD, first_name="Su", last_name="Per", is_active=True)
        for target in (self.other_admin, superuser, self.admin):
            with self.subTest(target=str(target)):
                response = self.client.post(self._url(target))
                self.assertEqual(response.status_code, 403)
                self.assertFalse(ImpersonationToken.objects.filter(member=target).exists())

    def test_the_button_shows_only_on_a_regular_members_page(self):
        regular_page = self.client.get(reverse("admin:authn_member_change", args=[self.regular.pk]))
        admin_page = self.client.get(reverse("admin:authn_member_change", args=[self.other_admin.pk]))

        self.assertContains(regular_page, "Login as Member")
        self.assertNotContains(admin_page, "Login as Member")


class MemberToolingAccessTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create_user(password=PASSWORD, first_name="Reg", last_name="Ular", is_active=True)
        self.owner = Member.objects.create_user(password=PASSWORD, is_staff=True, is_active=True)
        self.batch = MemberImportBatch.objects.create(
            created_by=self.owner, file_name="m.xlsx", file_sha256="0" * 64, expires_at="2999-01-01T00:00:00Z"
        )

    def test_a_member_who_is_not_an_admin_is_sent_to_the_admin_login(self):
        self.client.force_login(self.member)
        urls = [
            reverse("admin:authn_member_export_excel"),
            reverse("admin:authn_member_import_excel"),
            reverse("admin:authn_member_import_template"),
            *(reverse(f"admin:authn_member_import_{name}", args=[self.batch.pk]) for name in ("review", "result")),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("admin:login"), response["Location"])
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, "review")

    def test_an_admin_can_export_members(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("admin:authn_member_export_excel"))

        self.assertEqual(response.status_code, 200)
