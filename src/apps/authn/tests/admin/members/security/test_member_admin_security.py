"""Security regression tests for MemberAdmin authorization.

Covers two confirmed privilege-escalation findings:

* The custom ``impersonate`` admin URL was wrapped only in ``admin_site.admin_view``
  (is_staff only) — any staff member could mint a login token for a superuser.
* ``is_staff`` and ``admin_apps`` were freely editable on the Member change form,
  so a non-superuser admin could grant themselves every app / staff status.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ImpersonationToken, Member


def _staff(admin_apps=None, **kwargs):
    member = Member.objects.create_user(password="StrongPass123!", is_staff=True, is_active=True, **kwargs)
    if admin_apps is not None:
        member.admin_apps = admin_apps
        member.save(update_fields=["admin_apps"])
    return member


class ImpersonateAuthorizationTests(TestCase):
    """The impersonate URL must enforce authn-app access and refuse to mint a
    token for a privileged (staff/superuser) account."""

    def setUp(self):
        cache.clear()
        self.superuser = Member.objects.create_superuser(
            password="StrongPass123!", first_name="Super", last_name="User", is_active=True
        )
        self.regular_target = Member.objects.create_user(
            password="StrongPass123!", first_name="Reg", last_name="Ular", is_active=True
        )

    def tearDown(self):
        cache.clear()

    def _url(self, target):
        return reverse("admin:authn_member_impersonate", args=[target.pk])

    def test_non_authn_staff_cannot_impersonate_superuser(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        # Django converts the view's PermissionDenied into a 403 response.
        self.assertEqual(self.client.post(self._url(self.superuser)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=self.superuser).exists())

    def test_authn_admin_cannot_impersonate_superuser(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        self.client.force_login(authn_admin)
        self.assertEqual(self.client.post(self._url(self.superuser)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=self.superuser).exists())

    def test_authn_admin_cannot_impersonate_other_staff(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        other_staff = _staff(admin_apps=["mail"], first_name="Other", last_name="Staff")
        self.client.force_login(authn_admin)
        self.assertEqual(self.client.post(self._url(other_staff)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=other_staff).exists())

    def test_authn_admin_can_impersonate_regular_member(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        self.client.force_login(authn_admin)
        response = self.client.post(self._url(self.regular_target))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/impersonate-login#token=", response["Location"])
        self.assertTrue(ImpersonationToken.objects.filter(member=self.regular_target).exists())

    def test_superuser_can_impersonate_regular_member(self):
        self.client.force_login(self.superuser)
        response = self.client.post(self._url(self.regular_target))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ImpersonationToken.objects.filter(member=self.regular_target).exists())

    def test_superuser_cannot_impersonate_another_superuser(self):
        # Even I2G Master may not impersonate another privileged account.
        other_super = Member.objects.create_superuser(
            password="StrongPass123!", first_name="Other", last_name="Master", is_active=True
        )
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.post(self._url(other_super)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=other_super).exists())


class MemberToolingAuthorizationTests(TestCase):
    """The member import/export/template custom URLs expose or create PII member
    records, so they must require authn-app access — not merely is_staff."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_non_authn_staff_cannot_export_members(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        resp = self.client.get(reverse("admin:authn_member_export_excel"))
        self.assertEqual(resp.status_code, 403)

    def test_non_authn_staff_cannot_open_import(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        self.assertEqual(self.client.get(reverse("admin:authn_member_import_excel")).status_code, 403)

    def test_non_authn_staff_cannot_download_template(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        self.assertEqual(self.client.get(reverse("admin:authn_member_import_template")).status_code, 403)

    def test_non_authn_staff_get_403_on_every_import_review_url(self):
        from apps.authn.models import MemberImportBatch

        owner = _staff(admin_apps=["authn"], first_name="Owner", last_name="Admin")
        batch = MemberImportBatch.objects.create(
            created_by=owner, file_name="m.xlsx", file_sha256="0" * 64, expires_at="2999-01-01T00:00:00Z"
        )
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        for name in ("review", "confirm", "result", "discard"):
            url = reverse(f"admin:authn_member_import_{name}", args=[batch.pk])
            with self.subTest(name=name):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {"version": 0, "action": "save"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:authn_memberimportbatch_changelist")).status_code, 403)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "review")

    def test_authn_admin_can_export_members(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        self.client.force_login(authn_admin)
        resp = self.client.get(reverse("admin:authn_member_export_excel"))
        self.assertEqual(resp.status_code, 200)
