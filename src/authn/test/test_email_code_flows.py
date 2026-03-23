from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from authn.models import ContactEmail, EmailAuthChallenge

Member = get_user_model()


class EmailCodeAuthFlowTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.password = "StrongPass123!"
        self.member = Member.objects.create_user(
            username="member",
            email="member@example.com",
            password=self.password,
            is_active=True,
        )
        self.alias = ContactEmail.objects.create(
            member=self.member,
            email_address="alias@example.com",
            verified=True,
        )

    def test_password_login_accepts_verified_contact_email(self):
        response = self.client.post(
            "/authn/login/",
            {"email": self.alias.email_address, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], self.member.email)
        self.assertIn("access", response.data)

    def test_password_login_rejects_unverified_contact_email(self):
        unverified = ContactEmail.objects.create(
            member=self.member,
            email_address="pending@example.com",
            verified=False,
        )

        response = self.client.post(
            "/authn/login/",
            {"email": unverified.email_address, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["non_field_errors"][0], "Invalid credentials.")

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="123456")
    def test_login_code_flow_accepts_verified_contact_email(self, _mock_code, mock_send):
        request_response = self.client.post(
            "/authn/login/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(EmailAuthChallenge.objects.count(), 1)
        mock_send.assert_called_once()

        verify_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "123456"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["user"]["email"], self.member.email)
        self.assertEqual(EmailAuthChallenge.objects.first().status, EmailAuthChallenge.Status.CONSUMED)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="112233")
    def test_unified_email_auth_uses_login_flow_for_active_primary_email(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.member.email},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "login")
        self.assertEqual(request_response.data["next_step"], "verify_code")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": self.member.email, "code": "112233"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["next_step"], "account")
        self.assertFalse(verify_response.data["requires_profile_completion"])
        self.assertIn("access", verify_response.data)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="223344")
    def test_unified_email_auth_uses_login_flow_for_verified_contact_email(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "login")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": self.alias.email_address, "code": "223344"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["user"]["email"], self.member.email)
        self.assertEqual(verify_response.data["next_step"], "account")
        self.assertFalse(verify_response.data["requires_profile_completion"])

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="334455")
    def test_unified_email_auth_creates_pending_member_without_password(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "new-flow@example.com"},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "register")
        pending = Member.objects.get(email="new-flow@example.com")
        self.assertFalse(pending.is_active)
        self.assertFalse(pending.has_usable_password())
        self.assertEqual(pending.first_name, "")
        self.assertEqual(pending.organization, "")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": "new-flow@example.com", "code": "334455"},
            format="json",
        )

        pending.refresh_from_db()
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(pending.is_active)
        self.assertEqual(verify_response.data["next_step"], "complete_profile")
        self.assertTrue(verify_response.data["requires_profile_completion"])
        self.assertIn("access", verify_response.data)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="445566")
    def test_unified_email_auth_reuses_pending_member(self, _mock_code, _mock_send):
        pending = Member.objects.create_user(
            username="pending-email-auth",
            email="pending-flow@example.com",
            password="OldPass123!",
            is_active=False,
            first_name="Existing",
        )

        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "pending-flow@example.com"},
            format="json",
        )

        pending.refresh_from_db()
        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "register")
        self.assertEqual(Member.objects.filter(email="pending-flow@example.com").count(), 1)
        self.assertEqual(pending.first_name, "Existing")

    @patch("authn.services.email_challenges.send_auth_code_email")
    def test_unified_email_auth_rejects_conflicting_contact_email(self, _mock_send):
        ContactEmail.objects.create(
            member=self.member,
            email_address="blocked@example.com",
            verified=False,
        )

        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "blocked@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["email"], "This email cannot be used for registration.")
        self.assertEqual(EmailAuthChallenge.objects.count(), 0)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="654321")
    def test_register_creates_inactive_member_then_activates_on_verify(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/register/",
            {
                "email": "new-member@example.com",
                "password": self.password,
                "password_confirm": self.password,
                "first_name": "New",
                "last_name": "Member",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        member = Member.objects.get(email="new-member@example.com")
        self.assertFalse(member.is_active)

        verify_response = self.client.post(
            "/authn/register/verify-code/",
            {"email": "new-member@example.com", "code": "654321"},
            format="json",
        )

        member.refresh_from_db()
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(member.is_active)
        self.assertIn("access", verify_response.data)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="111111")
    def test_register_reuses_pending_member(self, _mock_code, _mock_send):
        pending = Member.objects.create_user(
            username="pending",
            email="pending@example.com",
            password="OldPass123!",
            is_active=False,
            first_name="Old",
        )

        response = self.client.post(
            "/authn/register/",
            {
                "email": "pending@example.com",
                "password": self.password,
                "password_confirm": self.password,
                "first_name": "Updated",
                "last_name": "User",
            },
            format="json",
        )

        pending.refresh_from_db()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(Member.objects.filter(email="pending@example.com").count(), 1)
        self.assertEqual(pending.first_name, "Updated")
        self.assertTrue(pending.check_password(self.password))

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="222222")
    def test_register_rejects_existing_contact_email(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/register/",
            {
                "email": self.alias.email_address,
                "password": self.password,
                "password_confirm": self.password,
                "first_name": "Alias",
                "last_name": "Conflict",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.data["email"][0])

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="333333")
    def test_password_reset_flow_works_with_verified_contact_email(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/password-reset/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )
        self.assertEqual(request_response.status_code, 202)

        verify_response = self.client.post(
            "/authn/password-reset/verify-code/",
            {"email": self.alias.email_address, "code": "333333"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        token = verify_response.data["verification_token"]

        confirm_response = self.client.post(
            "/authn/password-reset/confirm/",
            {
                "email": self.alias.email_address,
                "verification_token": token,
                "new_password": "NewStrongPass123!",
                "new_password_confirm": "NewStrongPass123!",
            },
            format="json",
        )

        self.member.refresh_from_db()
        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(self.member.check_password("NewStrongPass123!"))

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="444444")
    def test_authenticated_password_change_code_flow_uses_own_verified_emails(self, _mock_code, _mock_send):
        other_member = Member.objects.create_user(
            username="other",
            email="other@example.com",
            password="OtherPass123!",
            is_active=True,
        )
        other_alias = ContactEmail.objects.create(
            member=other_member,
            email_address="other-alias@example.com",
            verified=True,
        )

        self.client.force_authenticate(user=self.member)

        list_response = self.client.get("/authn/account-emails/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["emails"], [self.member.email, self.alias.email_address])

        invalid_request = self.client.post(
            "/authn/change-password/request-code/",
            {"email": other_alias.email_address},
            format="json",
        )
        self.assertEqual(invalid_request.status_code, 400)

        valid_request = self.client.post(
            "/authn/change-password/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )
        self.assertEqual(valid_request.status_code, 202)

        verify_response = self.client.post(
            "/authn/change-password/verify-code/",
            {"email": self.alias.email_address, "code": "444444"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        token = verify_response.data["verification_token"]

        confirm_response = self.client.post(
            "/authn/change-password/confirm/",
            {
                "verification_token": token,
                "new_password": "CodeChangedPass123!",
                "new_password_confirm": "CodeChangedPass123!",
            },
            format="json",
        )

        self.member.refresh_from_db()
        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(self.member.check_password("CodeChangedPass123!"))

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", side_effect=["555555", "666666"])
    def test_new_code_invalidates_previous_code(self, _mock_code, _mock_send):
        first_response = self.client.post(
            "/authn/login/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )
        self.assertEqual(first_response.status_code, 202)

        challenge = EmailAuthChallenge.objects.get(target_email=self.alias.email_address)
        challenge.last_sent_at = timezone.now() - timedelta(minutes=2)
        challenge.save(update_fields=["last_sent_at"])

        second_response = self.client.post(
            "/authn/login/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )
        self.assertEqual(second_response.status_code, 202)

        old_code_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "555555"},
            format="json",
        )
        self.assertEqual(old_code_response.status_code, 400)

        new_code_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "666666"},
            format="json",
        )
        self.assertEqual(new_code_response.status_code, 200)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="777777")
    def test_password_reset_confirm_requires_matching_email(self, _mock_code, _mock_send):
        """Correct token but wrong email → 400 'No eligible account found' (S10 fix)."""
        # Request + verify code for member
        self.client.post(
            "/authn/password-reset/request-code/",
            {"email": self.member.email},
            format="json",
        )
        verify_response = self.client.post(
            "/authn/password-reset/verify-code/",
            {"email": self.member.email, "code": "777777"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        token = verify_response.data["verification_token"]

        # Try to confirm with a non-existent email
        confirm_response = self.client.post(
            "/authn/password-reset/confirm/",
            {
                "email": "nobody@example.com",
                "verification_token": token,
                "new_password": "ResetPass123!",
                "new_password_confirm": "ResetPass123!",
            },
            format="json",
        )
        self.assertEqual(confirm_response.status_code, 400)
        self.assertIn("No eligible account found", str(confirm_response.data))

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="888888")
    def test_password_reset_confirm_rejects_other_users_token(self, _mock_code, _mock_send):
        """Member B's email + member A's token → 400 'Verification token is invalid' (S10 fix)."""
        other_member = Member.objects.create_user(
            username="other-reset",
            email="other-reset@example.com",
            password="OtherPass123!",
            is_active=True,
        )

        # Request + verify code for self.member (member A)
        self.client.post(
            "/authn/password-reset/request-code/",
            {"email": self.member.email},
            format="json",
        )
        verify_response = self.client.post(
            "/authn/password-reset/verify-code/",
            {"email": self.member.email, "code": "888888"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        token_a = verify_response.data["verification_token"]

        # Try to use member A's token with member B's email
        confirm_response = self.client.post(
            "/authn/password-reset/confirm/",
            {
                "email": other_member.email,
                "verification_token": token_a,
                "new_password": "ResetPass123!",
                "new_password_confirm": "ResetPass123!",
            },
            format="json",
        )
        self.assertEqual(confirm_response.status_code, 400)
        self.assertIn("Verification token is invalid", str(confirm_response.data))

    @patch("authn.services.email_challenges.send_auth_code_email")
    def test_password_reset_request_same_response_for_unknown_email(self, _mock_send):
        """Password reset for non-existent email should not reveal whether the email exists."""
        response = self.client.post(
            "/authn/password-reset/request-code/",
            {"email": "nonexistent@example.com"},
            format="json",
        )
        # Should return a success-like status (not 404) to prevent email enumeration
        self.assertIn(response.status_code, [200, 202])
