from unittest.mock import patch

from apps.authn.models import ContactEmail
from apps.authn.tests.account.contact_emails.test_contact_emails_crud import _ContactEmailCrudCase


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value="654321")
class ContactEmailCrudTests(_ContactEmailCrudCase):
    def test_make_primary_from_secondary_no_false_demotion(self, _mock_code, _mock_send):
        """Promoting the secondary itself should not trigger a spurious demotion to 'other'."""
        secondary = ContactEmail.objects.create(
            member=self.member, email_address="sec@example.com", email_type="secondary", verified=True
        )

        make_resp = self.client.post(f"/authn/contact-emails/{secondary.pk}/make-primary/")
        self.assertEqual(make_resp.status_code, 200)
        self.assertEqual(make_resp.data["email_type"], "primary")

        old_primary = ContactEmail.objects.get(email_address="primary@example.com")
        self.assertEqual(old_primary.email_type, "secondary")

        # Only two emails — neither should be "other"
        self.assertEqual(ContactEmail.objects.filter(member=self.member, email_type="other").count(), 0)

    def test_make_primary_cascades_demotion_when_secondary_exists(self, _mock_code, _mock_send):
        # Setup: primary + secondary + verified other
        ContactEmail.objects.create(
            member=self.member, email_address="sec@example.com", email_type="secondary", verified=True
        )
        third = ContactEmail.objects.create(
            member=self.member, email_address="third@example.com", email_type="other", verified=True
        )

        make_resp = self.client.post(f"/authn/contact-emails/{third.pk}/make-primary/")
        self.assertEqual(make_resp.status_code, 200)
        self.assertEqual(make_resp.data["email_type"], "primary")

        # Old primary → secondary, old secondary → other
        old_primary = ContactEmail.objects.get(email_address="primary@example.com")
        self.assertEqual(old_primary.email_type, "secondary")
        old_secondary = ContactEmail.objects.get(email_address="sec@example.com")
        self.assertEqual(old_secondary.email_type, "other")
