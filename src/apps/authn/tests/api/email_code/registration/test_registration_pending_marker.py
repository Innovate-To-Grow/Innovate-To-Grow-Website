from unittest.mock import patch

from django.test import TestCase
from rest_framework import serializers

from apps.authn.models import ContactEmail
from apps.authn.services import get_pending_registration_member, is_deactivated_member_email
from apps.authn.tests.api.email_code.registration.test_email_code_registration_pending import (
    Member,
    _run_admin_action,
)


class RegistrationPendingMarkerTests(TestCase):
    def setUp(self):
        self.site_admin = Member.objects.create_superuser(
            password="AdminPass123!", first_name="Site", last_name="Admin"
        )
        self.pending = Member.objects.create_user(is_active=False, registration_pending=True)
        ContactEmail.objects.create(member=self.pending, email_address="pending@example.com", email_type="primary")

    def test_lookups_distinguish_pending_from_deactivated(self):
        deactivated = Member.objects.create_user(is_active=False)
        ContactEmail.objects.create(member=deactivated, email_address="off@example.com", email_type="primary")

        self.assertEqual(get_pending_registration_member("Pending@Example.com"), self.pending)
        self.assertIsNone(get_pending_registration_member("off@example.com"))
        self.assertTrue(is_deactivated_member_email("OFF@example.com"))
        self.assertFalse(is_deactivated_member_email("pending@example.com"))
        self.assertFalse(is_deactivated_member_email(""))
        self.assertFalse(is_deactivated_member_email("nobody@example.com"))

    def test_any_activation_clears_the_marker(self):
        self.pending.is_active = True
        self.pending.save(update_fields=["is_active"])

        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertFalse(self.pending.registration_pending)

        # Re-deactivating through the change form (a plain save) leaves it non-pending.
        self.pending.is_active = False
        self.pending.save()
        self.assertIsNone(get_pending_registration_member("pending@example.com"))

    def test_admin_activate_action_clears_the_marker(self):
        _run_admin_action("activate_members", self.site_admin, self.pending)

        self.assertTrue(self.pending.is_active)
        self.assertFalse(self.pending.registration_pending)

    def test_admin_deactivate_action_ends_a_pending_signup(self):
        _run_admin_action("deactivate_members", self.site_admin, self.pending)

        self.assertFalse(self.pending.is_active)
        self.assertFalse(self.pending.registration_pending)
        self.assertIsNone(get_pending_registration_member("pending@example.com"))

    def test_password_register_cannot_write_after_admin_deactivation(self):
        from apps.authn.serializers.auth.register import RegisterSerializer

        original_password = self.pending.password
        serializer = RegisterSerializer(
            data={
                "email": "pending@example.com",
                "password": "encrypted",
                "password_confirm": "encrypted",
                "first_name": "Attacker",
                "last_name": "Changed",
                "organization": "Elsewhere",
            }
        )
        with patch("apps.authn.serializers.auth.register.decrypt_password_pair", return_value="NewStrongPass456!"):
            self.assertTrue(serializer.is_valid(), serializer.errors)

        # The serializer has cached a formerly pending Member. Deactivation
        # happens before save, as it can in a real concurrent request.
        _run_admin_action("deactivate_members", self.site_admin, self.pending)
        with patch("apps.authn.serializers.auth.register.issue_email_challenge") as issue_challenge:
            with self.assertRaises(serializers.ValidationError) as raised:
                serializer.save()

        self.assertEqual(raised.exception.detail["email"], "Unable to register with this email address.")
        issue_challenge.assert_not_called()
        self.pending.refresh_from_db()
        self.assertEqual((self.pending.first_name, self.pending.last_name), ("", ""))
        self.assertEqual(self.pending.password, original_password)
        self.assertFalse(self.pending.registration_pending)
