from django.contrib import admin
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import AdminInvitation, ContactEmail, ContactPhone, Member
from apps.authn.tests.admin.members.security.test_member_admin_security import _staff


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class PrivilegedTargetProtectionTests(TestCase):
    """A non-superuser with the ``authn`` grant must not be able to take over a privileged account.

    ``BaseModelAdmin``'s permissions are per-app and object-independent, which left two routes open:
    the password-reset view inherited from ``UserAdmin``, and attaching a verified contact record
    (a working admin sign-in factor) to a staff or superuser member.
    """

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

    def test_mark_verified_action_skips_privileged_owners(self):
        protected = ContactEmail.objects.create(
            member=self.master, email_address="master.alt2@example.com", email_type="secondary", verified=False
        )
        allowed = ContactEmail.objects.create(
            member=self.regular, email_address="reg.alt@example.com", email_type="secondary", verified=False
        )

        self.client.post(
            "/admin/authn/contactemail/",
            {
                "action": "mark_verified",
                "_selected_action": [str(protected.pk), str(allowed.pk)],
                "index": "0",
            },
        )

        protected.refresh_from_db()
        allowed.refresh_from_db()
        self.assertFalse(protected.verified)
        self.assertTrue(allowed.verified)

    def test_cannot_deactivate_a_superuser_via_the_bulk_action(self):
        self.client.post(
            "/admin/authn/member/",
            {
                "action": "deactivate_members",
                "_selected_action": [str(self.master.pk), str(self.regular.pk)],
                "index": "0",
            },
        )

        self.master.refresh_from_db()
        self.regular.refresh_from_db()
        self.assertTrue(self.master.is_active)
        self.assertFalse(self.regular.is_active)

    def test_is_active_is_readonly_for_a_privileged_target(self):
        model_admin = admin.site._registry[Member]
        request = RequestFactory().get("/")
        request.user = self.attacker

        self.assertIn("is_active", model_admin.get_readonly_fields(request, self.master))
        self.assertNotIn("is_active", model_admin.get_readonly_fields(request, self.regular))

    def test_make_primary_action_skips_a_superuser_email(self):
        """``make_primary`` re-points where a member's admin login codes are sent, so it takes the
        same owner guard as the sibling bulk actions."""
        protected = ContactEmail.objects.create(
            member=self.master, email_address="master.promote@example.com", email_type="secondary", verified=True
        )

        response = self.client.post(
            "/admin/authn/contactemail/",
            {
                "action": "make_primary",
                "_selected_action": [str(protected.pk)],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        protected.refresh_from_db()
        self.assertEqual(protected.email_type, "secondary")
        # The master's primary address — the login-code destination — is unchanged.
        self.assertTrue(
            ContactEmail.objects.filter(
                member=self.master, email_address="master@example.com", email_type="primary"
            ).exists()
        )

    def test_make_primary_action_still_works_for_an_ordinary_member(self):
        ContactEmail.objects.create(
            member=self.regular, email_address="reg.primary@example.com", email_type="primary", verified=True
        )
        secondary = ContactEmail.objects.create(
            member=self.regular, email_address="reg.secondary@example.com", email_type="secondary", verified=True
        )

        response = self.client.post(
            "/admin/authn/contactemail/",
            {
                "action": "make_primary",
                "_selected_action": [str(secondary.pk)],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        secondary.refresh_from_db()
        self.assertEqual(secondary.email_type, "primary")

    def test_delete_permission_denied_for_a_privileged_target(self):
        model_admin = admin.site._registry[Member]
        request = RequestFactory().get("/")
        request.user = self.attacker

        self.assertFalse(model_admin.has_delete_permission(request, self.master))
        self.assertTrue(model_admin.has_delete_permission(request, self.regular))

    def test_cannot_delete_a_superuser_via_the_delete_view(self):
        response = self.client.post(f"/admin/authn/member/{self.master.pk}/delete/", {"post": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Member.objects.filter(pk=self.master.pk).exists())

    def test_cannot_delete_a_superuser_via_the_bulk_action(self):
        response = self.client.post(
            "/admin/authn/member/",
            {
                "action": "delete_selected",
                "_selected_action": [str(self.master.pk), str(self.regular.pk)],
                "index": "0",
                "post": "yes",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Member.objects.filter(pk=self.master.pk).exists())
        # The guard refuses the whole selection, so the ordinary member survives too.
        self.assertTrue(Member.objects.filter(pk=self.regular.pk).exists())

    def test_can_delete_an_ordinary_member_via_the_delete_view(self):
        response = self.client.post(f"/admin/authn/member/{self.regular.pk}/delete/", {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Member.objects.filter(pk=self.regular.pk).exists())

    def test_can_delete_an_ordinary_member_via_the_bulk_action(self):
        response = self.client.post(
            "/admin/authn/member/",
            {
                "action": "delete_selected",
                "_selected_action": [str(self.regular.pk)],
                "index": "0",
                "post": "yes",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Member.objects.filter(pk=self.regular.pk).exists())

    def test_phone_normalize_apply_skips_privileged_owners(self):
        """The apply view rewrites phone rows across all owners; a non-superuser's run must not
        touch rows owned by members they cannot manage."""
        # bulk_create bypasses the model's save-time normalization, so both rows need fixing.
        ContactPhone.objects.bulk_create(
            [
                ContactPhone(member=self.master, phone_number="+12095551111", region="1-US"),
                ContactPhone(member=self.regular, phone_number="+12095552222", region="1-US"),
            ]
        )

        response = self.client.post(reverse("admin:authn_contactphone_normalize_apply"), {})

        self.assertEqual(response.status_code, 302)
        master_phone = ContactPhone.objects.get(member=self.master)
        regular_phone = ContactPhone.objects.get(member=self.regular)
        self.assertEqual(master_phone.phone_number, "+12095551111")
        self.assertEqual(regular_phone.phone_number, "2095552222")

    def test_invitation_token_hidden_from_view_only_staff(self):
        """The invitation token is a bearer credential for an is_staff account, so it renders only
        for superusers; view access itself stays."""
        invitation = AdminInvitation.objects.create(
            email="invitee@example.com",
            role=AdminInvitation.Role.ADMIN,
            token=AdminInvitation.generate_token(),
            status=AdminInvitation.Status.PENDING,
            expires_at=timezone.now() + timezone.timedelta(days=7),
            invited_by=self.master,
        )
        url = f"/admin/authn/admininvitation/{invitation.pk}/change/"

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(invitation.token, response.content.decode())

        self.client.force_login(self.master)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(invitation.token, response.content.decode())
