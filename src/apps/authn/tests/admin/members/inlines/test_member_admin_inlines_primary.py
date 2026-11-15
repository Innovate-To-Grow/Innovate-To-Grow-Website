from django.test import override_settings

from apps.authn.models import ContactEmail
from apps.authn.tests.admin.members.inlines.test_member_admin_inlines import _MemberAdminInlineUUIDSubmitCase


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class MemberAdminInlineUUIDSubmitTest(_MemberAdminInlineUUIDSubmitCase):
    def test_inline_rejects_primary_demotion(self):
        email = ContactEmail.objects.create(
            member=self.target,
            email_address="existing@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_emails-TOTAL_FORMS": "1",
                "contact_emails-INITIAL_FORMS": "1",
                "contact_emails-0-id": str(email.pk),
                "contact_emails-0-member": str(self.target.pk),
                "contact_emails-0-email_address": "existing@example.com",
                "contact_emails-0-email_type": "secondary",
                "contact_emails-0-verified": "on",
                "contact_emails-0-subscribe": "on",
            }
        )

        resp = self.client.post(self._change_url(), data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cannot be edited directly")
        email.refresh_from_db()
        self.assertEqual(email.email_type, "primary")

    def test_inline_rejects_primary_address_edit(self):
        email = ContactEmail.objects.create(
            member=self.target,
            email_address="existing@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_emails-TOTAL_FORMS": "1",
                "contact_emails-INITIAL_FORMS": "1",
                "contact_emails-0-id": str(email.pk),
                "contact_emails-0-member": str(self.target.pk),
                "contact_emails-0-email_address": "rewritten@example.com",
                "contact_emails-0-email_type": "primary",
                "contact_emails-0-verified": "on",
                "contact_emails-0-subscribe": "on",
            }
        )

        resp = self.client.post(self._change_url(), data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cannot be edited directly")
        email.refresh_from_db()
        self.assertEqual(email.email_address, "existing@example.com")

    def test_inline_rejects_primary_deletion(self):
        email = ContactEmail.objects.create(
            member=self.target,
            email_address="existing@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_emails-TOTAL_FORMS": "1",
                "contact_emails-INITIAL_FORMS": "1",
                "contact_emails-0-id": str(email.pk),
                "contact_emails-0-member": str(self.target.pk),
                "contact_emails-0-email_address": "existing@example.com",
                "contact_emails-0-email_type": "primary",
                "contact_emails-0-verified": "on",
                "contact_emails-0-subscribe": "on",
                "contact_emails-0-DELETE": "on",
            }
        )

        resp = self.client.post(self._change_url(), data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cannot be deleted directly")
        self.assertTrue(ContactEmail.objects.filter(pk=email.pk).exists())

    def test_inline_rejects_direct_primary_promotion(self):
        primary = ContactEmail.objects.create(
            member=self.target,
            email_address="primary@example.com",
            email_type="primary",
            verified=True,
        )
        secondary = ContactEmail.objects.create(
            member=self.target,
            email_address="secondary@example.com",
            email_type="secondary",
            verified=True,
        )
        self.client.force_login(self.admin)
        data = self._build_post_data()
        total_forms = int(data["contact_emails-TOTAL_FORMS"])
        secondary_index = next(
            index for index in range(total_forms) if data[f"contact_emails-{index}-id"] == str(secondary.pk)
        )
        data[f"contact_emails-{secondary_index}-email_type"] = "primary"

        resp = self.client.post(self._change_url(), data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cannot be assigned directly")
        primary.refresh_from_db()
        secondary.refresh_from_db()
        self.assertEqual(primary.email_type, "primary")
        self.assertEqual(secondary.email_type, "secondary")

    def test_empty_string_id_does_not_crash(self):
        """Some browsers may send an empty string instead of 'None'."""
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_emails-TOTAL_FORMS": "1",
                "contact_emails-INITIAL_FORMS": "0",
                "contact_emails-0-id": "",
                "contact_emails-0-member": "",
                "contact_emails-0-email_address": "empty-id@example.com",
                "contact_emails-0-email_type": "primary",
                "contact_emails-0-verified": "",
                "contact_emails-0-subscribe": "on",
            }
        )
        resp = self.client.post(self._change_url(), data)
        content = resp.content.decode() if resp.status_code == 200 else ""
        self.assertNotIn("is not a valid UUID", content)
