from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from authn.models import ContactEmail

Member = get_user_model()


class ContactEmailTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.member = Member.objects.create_user(
            username="testuser",
            email="primary@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.other_member = Member.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.client.force_authenticate(user=self.member)

    # ── List ─────────────────────────────────────────────

    def test_list_contact_emails_empty(self):
        response = self.client.get("/authn/contact-emails/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    # ── Create ───────────────────────────────────────────

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="123456")
    def test_create_sends_verification_code(self, _mock_code, mock_send):
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "secondary@example.com", "email_type": "secondary", "subscribe": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["verified"])
        self.assertEqual(response.data["email_address"], "secondary@example.com")
        self.assertEqual(response.data["email_type"], "secondary")
        self.assertTrue(response.data["subscribe"])
        mock_send.assert_called_once()

    @patch("authn.services.email_challenges.send_auth_code_email")
    def test_create_rejects_duplicate_member_email(self, _mock_send):
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "primary@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="111111")
    def test_create_rejects_duplicate_contact_email(self, _mock_code, _mock_send):
        ContactEmail.objects.create(
            member=self.other_member,
            email_address="taken@example.com",
            verified=True,
        )
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "taken@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_primary_type(self):
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "new@example.com", "email_type": "primary"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    # ── Verify ───────────────────────────────────────────

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="654321")
    def test_verify_code_marks_verified(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "verify-me@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        verify_resp = self.client.post(
            f"/authn/contact-emails/{contact_id}/verify-code/",
            {"code": "654321"},
            format="json",
        )
        self.assertEqual(verify_resp.status_code, 200)
        self.assertTrue(verify_resp.data["verified"])

        contact = ContactEmail.objects.get(pk=contact_id)
        self.assertTrue(contact.verified)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="654321")
    def test_verify_code_rejects_wrong_code(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "wrong-code@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        verify_resp = self.client.post(
            f"/authn/contact-emails/{contact_id}/verify-code/",
            {"code": "000000"},
            format="json",
        )
        self.assertEqual(verify_resp.status_code, 400)

    # ── Update ───────────────────────────────────────────

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="111111")
    def test_update_type_and_subscribe(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "update-me@example.com", "email_type": "secondary"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        patch_resp = self.client.patch(
            f"/authn/contact-emails/{contact_id}/",
            {"email_type": "other", "subscribe": True},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.data["email_type"], "other")
        self.assertTrue(patch_resp.data["subscribe"])

    def test_update_rejects_primary_type(self):
        contact = ContactEmail.objects.create(
            member=self.member,
            email_address="existing@example.com",
            email_type="secondary",
        )
        response = self.client.patch(
            f"/authn/contact-emails/{contact.pk}/",
            {"email_type": "primary"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="111111")
    def test_update_ignores_email_address(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "immutable@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        patch_resp = self.client.patch(
            f"/authn/contact-emails/{contact_id}/",
            {"email_address": "changed@example.com", "subscribe": True},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.data["email_address"], "immutable@example.com")

    # ── Delete ───────────────────────────────────────────

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="111111")
    def test_delete_returns_204(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "delete-me@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        delete_resp = self.client.delete(f"/authn/contact-emails/{contact_id}/")
        self.assertEqual(delete_resp.status_code, 204)

        # Soft-deleted: visible via all_objects only
        self.assertFalse(ContactEmail.objects.filter(pk=contact_id).exists())

    # ── Scoping ──────────────────────────────────────────

    def test_cannot_access_other_users_email(self):
        contact = ContactEmail.objects.create(
            member=self.other_member,
            email_address="not-mine@example.com",
            verified=True,
        )
        self.client.get(f"/authn/contact-emails/{contact.pk}/")
        # Detail endpoint doesn't support GET, but PATCH/DELETE should 404
        patch_resp = self.client.patch(
            f"/authn/contact-emails/{contact.pk}/",
            {"subscribe": True},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 404)

        delete_resp = self.client.delete(f"/authn/contact-emails/{contact.pk}/")
        self.assertEqual(delete_resp.status_code, 404)

    # ── Resend ───────────────────────────────────────────

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="111111")
    def test_resend_verification_on_unverified(self, _mock_code, mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "resend-me@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]
        mock_send.reset_mock()

        # Clear cooldown
        from authn.models.security import EmailAuthChallenge

        EmailAuthChallenge.objects.filter(target_email="resend-me@example.com").update(last_sent_at=None)

        resend_resp = self.client.post(f"/authn/contact-emails/{contact_id}/request-verification/")
        self.assertEqual(resend_resp.status_code, 202)
        mock_send.assert_called_once()

    def test_resend_rejects_already_verified(self):
        contact = ContactEmail.objects.create(
            member=self.member,
            email_address="already-verified@example.com",
            verified=True,
        )
        response = self.client.post(f"/authn/contact-emails/{contact.pk}/request-verification/")
        self.assertEqual(response.status_code, 400)

    # ── Profile email_subscribe ──────────────────────────

    def test_profile_includes_email_subscribe(self):
        response = self.client.get("/authn/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("email_subscribe", response.data)
        self.assertTrue(response.data["email_subscribe"])

    def test_patch_profile_email_subscribe(self):
        response = self.client.patch(
            "/authn/profile/",
            {"email_subscribe": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["email_subscribe"])

        self.member.refresh_from_db()
        self.assertFalse(self.member.email_subscribe)

    # ── Account emails integration ───────────────────────

    def test_unverified_email_excluded_from_account_emails(self):
        ContactEmail.objects.create(
            member=self.member,
            email_address="unverified@example.com",
            verified=False,
        )
        response = self.client.get("/authn/account-emails/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("unverified@example.com", response.data["emails"])

    @patch("authn.services.email_challenges.send_auth_code_email")
    @patch("authn.services.email_challenges._random_code", return_value="999999")
    def test_verified_email_included_in_account_emails(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "will-verify@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        self.client.post(
            f"/authn/contact-emails/{contact_id}/verify-code/",
            {"code": "999999"},
            format="json",
        )

        response = self.client.get("/authn/account-emails/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("will-verify@example.com", response.data["emails"])

    # ── Cross-user scope enforcement ──────────────────────

    @patch("authn.services.email_challenges.send_auth_code_email")
    def test_cannot_verify_other_users_email(self, _mock_send):
        """Verify that a user cannot verify another user's contact email."""
        # Create contact email for other_member
        self.client.force_authenticate(user=self.other_member)
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "other-contact@example.com"},
            format="json",
        )
        other_contact_id = create_resp.data["id"]

        # Switch to self.member and try to verify other_member's email
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            f"/authn/contact-emails/{other_contact_id}/verify-code/",
            {"code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    @patch("authn.services.email_challenges.send_auth_code_email")
    def test_cannot_request_verification_for_other_users_email(self, _mock_send):
        """Verify that a user cannot request verification for another user's contact email."""
        self.client.force_authenticate(user=self.other_member)
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "other-contact2@example.com"},
            format="json",
        )
        other_contact_id = create_resp.data["id"]

        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            f"/authn/contact-emails/{other_contact_id}/request-verification/",
            format="json",
        )
        self.assertEqual(response.status_code, 404)
