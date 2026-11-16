from unittest.mock import patch

from apps.authn.admin.members.contact.phone import ContactPhoneAdmin
from apps.authn.admin.security.rsa_keypair import RSAKeypairAdmin
from apps.authn.models import (
    ContactPhone,
    RSAKeypair,
)
from apps.authn.tests.admin.actions.test_admin_actions import Member, _AdminTestBase, _request


class ContactPhoneAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.model_admin = ContactPhoneAdmin(ContactPhone, self.site)
        self.member = Member.objects.create_user(password="t", first_name="C", last_name="P")
        self.phone = ContactPhone.objects.create(member=self.member, phone_number="2095551234", region="1-US")

    def test_get_formatted_number(self):
        result = self.model_admin.get_formatted_number(self.phone)
        self.assertTrue(result)

    def test_there_is_no_bulk_mark_verified_action(self):
        # A verified number signs in by SMS: only a code verifies it, never a bulk action.
        request = _request(self.rf, self.admin_user)
        actions = self.model_admin.get_actions(request)
        self.assertNotIn("mark_verified", actions)
        self.assertIn("mark_unverified", actions)

    def test_mark_unverified(self):
        self.phone.verified = True
        self.phone.save(update_fields=["verified"])
        request = _request(self.rf, self.admin_user)
        self.model_admin.mark_unverified(request, ContactPhone.objects.filter(pk=self.phone.pk))
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.verified)
        self.assertIn("1 phone(s) marked as unverified.", self._messages(request))

    def test_normalize_all_phones_redirects_to_preview(self):
        request = _request(self.rf, self.admin_user)
        response = self.model_admin.normalize_all_phones(request, ContactPhone.objects.all())
        self.assertEqual(response.status_code, 302)
        self.assertIn("normalize-phones-preview", response.url)

    def test_normalize_preview_view(self):
        # store a number that needs normalization (E.164 with country code)
        ContactPhone.objects.create(member=self.member, phone_number="+12095559999", region="1-US")
        request = _request(self.rf, self.admin_user)
        response = self.model_admin._normalize_preview_view(request)
        self.assertEqual(response.status_code, 200)

    def test_normalize_apply_view_get_redirects(self):
        request = _request(self.rf, self.admin_user)
        response = self.model_admin._normalize_apply_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("normalize-phones-preview", response.url)

    def test_normalize_apply_view_post_applies(self):
        ContactPhone.objects.create(member=self.member, phone_number="+12095559999", region="1-US")
        request = _request(self.rf, self.admin_user, method="post")
        response = self.model_admin._normalize_apply_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("contactphone", response.url)
        self.assertTrue(self._messages(request))

    def test_normalize_apply_view_handles_exception(self):
        request = _request(self.rf, self.admin_user, method="post")
        with patch(
            "apps.authn.admin.members.contact.normalization_views.apply_phone_changes",
            side_effect=RuntimeError("boom"),
        ):
            response = self.model_admin._normalize_apply_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("normalize-phones-preview", response.url)
        self.assertTrue(any("Failed to apply" in m for m in self._messages(request)))


class RSAKeypairAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.model_admin = RSAKeypairAdmin(RSAKeypair, self.site)
        public_pem, private_pem = RSAKeypair.generate_keypair()
        self.keypair = RSAKeypair.objects.create(
            name="K1", public_key_pem=public_pem, private_key_pem=private_pem, is_active=True
        )

    def test_get_readonly_fields_for_existing(self):
        fields = self.model_admin.get_readonly_fields(None, obj=self.keypair)
        self.assertIn("private_key_pem", fields)
        self.assertIn("is_active", fields)

    def test_get_readonly_fields_for_new(self):
        fields = self.model_admin.get_readonly_fields(None, obj=None)
        self.assertEqual(fields, ("key_id",))

    def test_get_fieldsets_for_existing(self):
        fieldsets = self.model_admin.get_fieldsets(None, obj=self.keypair)
        self.assertEqual(len(fieldsets), 3)

    def test_get_fieldsets_for_new(self):
        fieldsets = self.model_admin.get_fieldsets(None, obj=None)
        self.assertEqual(len(fieldsets), 1)

    def test_deactivate_keypairs(self):
        request = _request(self.rf, self.admin_user)
        self.model_admin.deactivate_keypairs(request, RSAKeypair.objects.filter(pk=self.keypair.pk))
        self.keypair.refresh_from_db()
        self.assertFalse(self.keypair.is_active)
        self.assertIn("1 keypair(s) deactivated.", self._messages(request))

    def test_retired_keypairs_cannot_be_reactivated_from_admin(self):
        self.keypair.is_active = False
        self.keypair.save(update_fields=["is_active"])

        self.assertNotIn("activate_keypairs", self.model_admin.actions)
        self.assertFalse(hasattr(self.model_admin, "activate_keypairs"))
        self.keypair.refresh_from_db()
        self.assertFalse(self.keypair.is_active)

    def test_regenerate_keys(self):
        old_pub = self.keypair.public_key_pem
        request = _request(self.rf, self.admin_user)
        self.model_admin.regenerate_keys(request, RSAKeypair.objects.filter(pk=self.keypair.pk))
        self.keypair.refresh_from_db()
        replacement = RSAKeypair.objects.get(name=self.keypair.name, is_active=True)
        self.assertEqual(self.keypair.public_key_pem, old_pub)
        self.assertFalse(self.keypair.is_active)
        self.assertNotEqual(replacement.public_key_pem, old_pub)
        self.assertIn("1 keypair(s) regenerated.", self._messages(request))
