from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail, Member
from apps.authn.tests.admin.members.security.privileged.test_member_admin_security import _staff


class _PrivilegedTargetProtectionCase(TestCase):
    def setUp(self):
        cache.clear()
        self.attacker = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        ContactEmail.objects.create(
            member=self.attacker, email_address="authnadmin@example.com", email_type="primary", verified=True
        )
        self.master = Member.objects.create_superuser(
            password="StrongPass123!", first_name="I2G", last_name="Master", is_active=True
        )
        ContactEmail.objects.create(
            member=self.master, email_address="master@example.com", email_type="primary", verified=True
        )
        self.regular = Member.objects.create_user(
            password="StrongPass123!", first_name="Reg", last_name="Ular", is_active=True
        )
        self.client.force_login(self.attacker)

    def tearDown(self):
        cache.clear()

    @staticmethod
    def _password_url(target):
        return f"/admin/authn/member/{target.pk}/password/"


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class PrivilegedTargetProtectionTests(_PrivilegedTargetProtectionCase):
    """A non-superuser with the ``authn`` grant must not be able to take over a privileged account.

    ``BaseModelAdmin``'s permissions are per-app and object-independent, which left two routes open:
    the password-reset view inherited from ``UserAdmin``, and attaching a verified contact record
    (a working admin sign-in factor) to a staff or superuser member.
    """

    def test_cannot_reset_a_superuser_password(self):
        old_hash = self.master.password

        response = self.client.get(self._password_url(self.master))

        self.assertEqual(response.status_code, 403)
        self.master.refresh_from_db()
        self.assertEqual(self.master.password, old_hash)

    def test_cannot_post_a_new_superuser_password(self):
        old_hash = self.master.password

        response = self.client.post(
            self._password_url(self.master),
            {"password1": "Pwned!12345", "password2": "Pwned!12345"},
        )

        self.assertEqual(response.status_code, 403)
        self.master.refresh_from_db()
        self.assertEqual(self.master.password, old_hash)

    def test_can_reset_a_regular_member_password(self):
        old_hash = self.regular.password

        response = self.client.post(
            self._password_url(self.regular),
            {"password1": "BrandNew!12345", "password2": "BrandNew!12345"},
        )

        self.assertEqual(response.status_code, 302)
        self.regular.refresh_from_db()
        self.assertNotEqual(self.regular.password, old_hash)

    def test_can_reset_own_password(self):
        old_hash = self.attacker.password

        response = self.client.post(
            self._password_url(self.attacker),
            {"password1": "MyOwnNew!12345", "password2": "MyOwnNew!12345"},
        )

        self.assertEqual(response.status_code, 302)
        self.attacker.refresh_from_db()
        self.assertNotEqual(self.attacker.password, old_hash)

    def test_superuser_can_reset_another_superuser_password(self):
        self.client.force_login(self.master)
        other = Member.objects.create_superuser(
            password="StrongPass123!", first_name="Other", last_name="Master", is_active=True
        )
        old_hash = other.password

        response = self.client.post(
            self._password_url(other), {"password1": "Rotated!12345", "password2": "Rotated!12345"}
        )

        self.assertEqual(response.status_code, 302)
        other.refresh_from_db()
        self.assertNotEqual(other.password, old_hash)

    def test_cannot_attach_a_verified_contact_email_to_a_superuser(self):
        response = self.client.post(
            "/admin/authn/contactemail/add/",
            {
                "member": str(self.master.pk),
                "email_address": "attacker@evil.test",
                "email_type": "secondary",
                "verified": "on",
                "subscribe": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 200)  # re-rendered with a validation error
        self.assertFalse(ContactEmail.objects.filter(email_address="attacker@evil.test").exists())

    def test_can_attach_a_contact_email_to_a_regular_member(self):
        response = self.client.post(
            "/admin/authn/contactemail/add/",
            {
                "member": str(self.regular.pk),
                "email_address": "ok@example.test",
                "email_type": "secondary",
                "subscribe": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.assertTrue(ContactEmail.objects.filter(email_address="ok@example.test").exists())

    def test_a_superuser_contact_email_renders_read_only(self):
        """View access is still granted, so Django renders the view-only form: no Save, no inputs."""
        row = ContactEmail.objects.create(
            member=self.master, email_address="master.alt@example.com", email_type="secondary", verified=False
        )

        response = self.client.get(f"/admin/authn/contactemail/{row.pk}/change/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('name="_save"', content)
        self.assertNotIn('name="email_address"', content)
        self.assertNotIn('name="verified"', content)

    def test_cannot_post_a_change_to_a_superuser_contact_email(self):
        row = ContactEmail.objects.create(
            member=self.master, email_address="master.alt3@example.com", email_type="secondary", verified=False
        )

        response = self.client.post(
            f"/admin/authn/contactemail/{row.pk}/change/",
            {
                "member": str(self.master.pk),
                "email_address": "master.alt3@example.com",
                "email_type": "secondary",
                "verified": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 403)
        row.refresh_from_db()
        self.assertFalse(row.verified)
