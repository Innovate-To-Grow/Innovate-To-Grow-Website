from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from authn.models import ContactEmail

Member = get_user_model()


@patch("authn.services.email.send_email.send_verification_email")
@patch("authn.services.email_challenges._random_code", return_value="654321")
class ContactEmailCrudTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.member = Member.objects.create_user(
            password="StrongPass123!",
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.member, email_address="primary@example.com", email_type="primary", verified=True
        )
        self.other_member = Member.objects.create_user(
            password="StrongPass123!",
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.other_member, email_address="other@example.com", email_type="primary", verified=True
        )
        self.client.force_authenticate(user=self.member)

    # ── List ─────────────────────────────────────────────

    def test_list_contact_emails_shows_primary(self, _mock_code, _mock_send):
        response = self.client.get("/authn/contact-emails/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["email_address"], "primary@example.com")

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

    def test_create_rejects_duplicate_member_email(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "primary@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

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

    def test_create_rejects_primary_type(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "new@example.com", "email_type": "primary"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

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

    def test_update_rejects_primary_type(self, _mock_code, _mock_send):
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
