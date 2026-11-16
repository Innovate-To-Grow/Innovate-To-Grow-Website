from unittest.mock import patch

from apps.authn.models import ContactEmail
from apps.authn.tests.account.contact_emails.test_contact_emails_crud import _ContactEmailCrudCase


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value="654321")
class ContactEmailCrudTests(_ContactEmailCrudCase):
    def test_delete_returns_204(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "delete-me@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        delete_resp = self.client.delete(f"/authn/contact-emails/{contact_id}/")
        self.assertEqual(delete_resp.status_code, 204)

        self.assertFalse(ContactEmail.objects.filter(pk=contact_id).exists())

    def test_make_primary_swaps_types(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "new-primary@example.com"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        new_id = create_resp.data["id"]

        verify_resp = self.client.post(
            f"/authn/contact-emails/{new_id}/verify-code/",
            {"code": "654321"},
            format="json",
        )
        self.assertEqual(verify_resp.status_code, 200)

        make_resp = self.client.post(f"/authn/contact-emails/{new_id}/make-primary/")
        self.assertEqual(make_resp.status_code, 200)
        self.assertEqual(make_resp.data["email_type"], "primary")
        self.assertEqual(make_resp.data["email_address"], "new-primary@example.com")

        old_primary = ContactEmail.objects.get(email_address="primary@example.com")
        self.assertEqual(old_primary.email_type, "secondary")

        profile_resp = self.client.get("/authn/profile/")
        self.assertEqual(profile_resp.status_code, 200)
        self.assertEqual(profile_resp.data["email"], "new-primary@example.com")
        self.assertEqual(str(profile_resp.data["primary_email_id"]), str(new_id))

    def test_make_primary_rejects_unverified(self, _mock_code, _mock_send):
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "not-verified@example.com"},
            format="json",
        )
        contact_id = create_resp.data["id"]

        make_resp = self.client.post(f"/authn/contact-emails/{contact_id}/make-primary/")
        self.assertEqual(make_resp.status_code, 400)
        self.assertIn("detail", make_resp.data)

    def test_make_primary_idempotent_on_primary(self, _mock_code, _mock_send):
        primary = ContactEmail.objects.get(member=self.member, email_type="primary")
        make_resp = self.client.post(f"/authn/contact-emails/{primary.pk}/make-primary/")
        self.assertEqual(make_resp.status_code, 200)
        self.assertEqual(make_resp.data["email_type"], "primary")

    def test_create_rejects_second_secondary_email(self, _mock_code, _mock_send):
        first = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "sec1@example.com", "email_type": "secondary"},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "sec2@example.com", "email_type": "secondary"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_allows_other_when_secondary_exists(self, _mock_code, _mock_send):
        first = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "sec@example.com", "email_type": "secondary"},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "extra@example.com", "email_type": "other"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["email_type"], "other")

    def test_update_rejects_changing_to_secondary_when_one_exists(self, _mock_code, _mock_send):
        first = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "sec@example.com", "email_type": "secondary"},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "other@example2.com", "email_type": "other"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        other_id = create_resp.data["id"]
        patch_resp = self.client.patch(
            f"/authn/contact-emails/{other_id}/",
            {"email_type": "secondary"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 400)

    def test_update_allows_secondary_to_secondary_noop(self, _mock_code, _mock_send):
        """Patching an already-secondary email to 'secondary' should succeed (no-op)."""
        contact = ContactEmail.objects.create(
            member=self.member, email_address="sec@example.com", email_type="secondary"
        )
        patch_resp = self.client.patch(
            f"/authn/contact-emails/{contact.pk}/",
            {"email_type": "secondary"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.data["email_type"], "secondary")

    def test_update_other_to_secondary_when_none_exists(self, _mock_code, _mock_send):
        """Changing 'other' to 'secondary' should work when no secondary email exists."""
        contact = ContactEmail.objects.create(member=self.member, email_address="extra@example.com", email_type="other")
        patch_resp = self.client.patch(
            f"/authn/contact-emails/{contact.pk}/",
            {"email_type": "secondary"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.data["email_type"], "secondary")

    def test_create_secondary_after_deleting_previous(self, _mock_code, _mock_send):
        """After deleting the secondary, creating a new one should succeed."""
        create_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "sec1@example.com", "email_type": "secondary"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        sec_id = create_resp.data["id"]

        delete_resp = self.client.delete(f"/authn/contact-emails/{sec_id}/")
        self.assertEqual(delete_resp.status_code, 204)

        new_resp = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "sec2@example.com", "email_type": "secondary"},
            format="json",
        )
        self.assertEqual(new_resp.status_code, 201)
        self.assertEqual(new_resp.data["email_type"], "secondary")

    def test_secondary_constraint_is_per_member(self, _mock_code, _mock_send):
        """Another member's secondary should not block this member from creating one."""
        ContactEmail.objects.create(
            member=self.other_member, email_address="other-sec@example.com", email_type="secondary"
        )
        response = self.client.post(
            "/authn/contact-emails/",
            {"email_address": "my-sec@example.com", "email_type": "secondary"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["email_type"], "secondary")
