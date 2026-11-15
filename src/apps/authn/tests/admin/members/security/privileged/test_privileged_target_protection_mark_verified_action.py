from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.tests.admin.members.security.privileged.test_privileged_target_protection import (
    _PrivilegedTargetProtectionCase,
)


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class PrivilegedTargetProtectionTests(_PrivilegedTargetProtectionCase):
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
