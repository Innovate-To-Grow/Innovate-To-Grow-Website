from unittest.mock import patch

from apps.authn.models import ContactEmail
from apps.authn.services import claim_unclaimed_contact_email
from apps.authn.tests.api.email_code.login.test_email_code_logins import Member, _EmailCodeAuthLoginCase


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value="654321")
class EmailCodeAuthLoginTests(_EmailCodeAuthLoginCase):
    def test_unified_email_auth_defaults_event_to_empty(self, _mock_code, mock_send):
        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.primary_email.email_address, "source": "event_registration"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mock_send.call_args.kwargs["link_event"], "")

    def test_unified_email_auth_rejects_invalid_event_slug(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.primary_email.email_address, "source": "event_registration", "event": "bad slug!"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unified_email_auth_forwards_event_slug_on_register_branch(self, _mock_code, mock_send):
        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "brand-new@example.com", "source": "event_registration", "event": "demo-day"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mock_send.call_args.kwargs["link_event"], "demo-day")

    def test_unified_email_auth_uses_login_flow_for_verified_contact_email(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertNotIn("flow", request_response.data)

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": self.alias.email_address, "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["user"]["email"], self.primary_email.email_address)
        self.assertEqual(verify_response.data["next_step"], "complete_profile")
        self.assertTrue(verify_response.data["requires_profile_completion"])

    def test_unified_email_auth_creates_pending_member_without_password(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "new-flow@example.com"},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertNotIn("flow", request_response.data)
        primary_contact = ContactEmail.objects.get(email_address="new-flow@example.com")
        pending = primary_contact.member
        self.assertFalse(pending.is_active)
        self.assertFalse(pending.has_usable_password())
        self.assertEqual(pending.first_name, "")
        self.assertEqual(pending.organization, "")
        self.assertTrue(primary_contact.subscribe)

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": "new-flow@example.com", "code": "654321"},
            format="json",
        )

        pending.refresh_from_db()
        primary_contact.refresh_from_db()
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(pending.is_active)
        self.assertTrue(primary_contact.subscribe)
        self.assertEqual(verify_response.data["next_step"], "complete_profile")
        self.assertTrue(verify_response.data["requires_profile_completion"])
        self.assertIn("access", verify_response.data)

    def test_unified_email_auth_claims_unowned_subscriber_contact(self, _mock_code, _mock_send):
        ContactEmail.objects.create(
            email_address="subscriber@example.com",
            email_type="other",
            subscribe=True,
        )

        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "subscriber@example.com", "source": "event_registration"},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(ContactEmail.objects.filter(email_address="subscriber@example.com").count(), 1)
        contact = ContactEmail.objects.get(email_address="subscriber@example.com")
        pending = contact.member
        self.assertIsNotNone(pending)
        self.assertEqual(contact.email_type, "primary")
        self.assertFalse(contact.verified)
        self.assertTrue(contact.subscribe)
        self.assertFalse(pending.is_active)

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": "subscriber@example.com", "code": "654321"},
            format="json",
        )

        pending.refresh_from_db()
        contact.refresh_from_db()
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(pending.is_active)
        self.assertTrue(contact.verified)
        self.assertTrue(contact.subscribe)

    def test_claim_unowned_subscriber_contact_does_not_overwrite_existing_claim(self, _mock_code, _mock_send):
        first_member = Member.objects.create_user(password="FirstPass123!", is_active=False)
        second_member = Member.objects.create_user(password="SecondPass123!", is_active=False)
        contact = ContactEmail.objects.create(
            email_address="claim-race@example.com",
            email_type="other",
            subscribe=True,
        )

        first_claim = claim_unclaimed_contact_email(contact.email_address, member=first_member)
        second_claim = claim_unclaimed_contact_email(contact.email_address, member=second_member)

        contact.refresh_from_db()
        self.assertIsNotNone(first_claim)
        self.assertIsNone(second_claim)
        self.assertEqual(contact.member_id, first_member.pk)
        self.assertEqual(contact.email_type, "primary")
        self.assertFalse(contact.verified)

    def test_unified_email_auth_reuses_pending_member(self, _mock_code, _mock_send):
        pending = Member.objects.create_user(
            password="OldPass123!",
            is_active=False,
            registration_pending=True,
            first_name="Existing",
        )
        ContactEmail.objects.create(
            member=pending, email_address="pending-flow@example.com", email_type="primary", verified=True
        )

        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "pending-flow@example.com"},
            format="json",
        )

        pending.refresh_from_db()
        self.assertEqual(request_response.status_code, 202)
        self.assertNotIn("flow", request_response.data)
        self.assertEqual(ContactEmail.objects.filter(email_address="pending-flow@example.com").count(), 1)
        self.assertEqual(pending.first_name, "Existing")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": "pending-flow@example.com", "code": "654321"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(ContactEmail.objects.get(email_address="pending-flow@example.com").subscribe)
