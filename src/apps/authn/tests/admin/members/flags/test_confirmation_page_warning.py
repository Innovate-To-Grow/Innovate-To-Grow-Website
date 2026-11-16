from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.admin.members.flags.test_sign_in_warning import Member, WarningFixture
from apps.authn.tests.helpers import scrape_admin_form


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmationPageWarningTests(WarningFixture):
    def confirmation(self, url, data):
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/confirm-change/", response["Location"])
        return self.client.get(response["Location"])

    def test_the_member_page_warns_before_the_save(self):
        page = self.confirmation(self.member_url(self.jane), self.member_page(self.jane, untick=[self.jane_primary]))

        self.assertContains(page, "Warning: signing in")
        self.assertContains(page, "No verified email or phone left")
        self.assertTrue(ContactEmail.objects.get(pk=self.jane_primary.pk).verified)  # nothing saved yet

    def test_the_member_page_does_not_warn_for_other_edits(self):
        page = self.confirmation(self.member_url(self.jane), self.member_page(self.jane, overrides={"title": "Dean"}))

        self.assertNotContains(page, "Warning: signing in")

    def test_a_contact_email_page_warns_before_the_save(self):
        url = reverse("admin:authn_contactemail_change", args=[self.jane_primary.pk])
        data = scrape_admin_form(self.client, url)
        data.pop("verified", None)

        page = self.confirmation(url, data)

        self.assertContains(page, "Warning: signing in")

    def test_a_contact_phone_page_warns_before_the_save(self):
        url = reverse("admin:authn_contactphone_change", args=[self.pat_phone.pk])
        data = scrape_admin_form(self.client, url)
        data.pop("verified", None)

        page = self.confirmation(url, data)

        self.assertContains(page, "Warning: signing in")

    def test_moving_the_last_verified_address_to_someone_else_warns(self):
        other = Member.objects.create_user(first_name="Otto", last_name="Other", is_active=True)
        backup = ContactEmail.objects.create(
            member=self.jane, email_address="jane.work@example.com", email_type="secondary", verified=True
        )
        ContactEmail.objects.filter(pk=self.jane_primary.pk).update(verified=False)
        url = reverse("admin:authn_contactemail_change", args=[backup.pk])

        page = self.confirmation(url, scrape_admin_form(self.client, url, {"member": str(other.pk)}))

        self.assertContains(page, "Warning: signing in")

    def test_removing_the_last_verified_row_on_the_member_page_warns_before_the_save(self):
        ContactEmail.objects.filter(pk=self.jane_primary.pk).update(verified=False)
        backup = ContactEmail.objects.create(
            member=self.jane, email_address="jane.work@example.com", email_type="secondary", verified=True
        )

        page = self.confirmation(self.member_url(self.jane), self.member_page(self.jane, delete=[backup]))

        self.assertContains(page, "Warning: signing in")
        self.assertTrue(ContactEmail.objects.filter(pk=backup.pk).exists())  # nothing saved yet

    def test_unticking_one_of_several_verified_contacts_does_not_warn(self):
        ContactPhone.objects.create(member=self.jane, phone_number="2095550122", verified=True)
        url = reverse("admin:authn_contactemail_change", args=[self.jane_primary.pk])
        data = scrape_admin_form(self.client, url)
        data.pop("verified", None)

        page = self.confirmation(url, data)

        self.assertNotContains(page, "Warning: signing in")

    def test_an_unlinked_address_never_warns(self):
        unlinked = ContactEmail.objects.create(email_address="nobody@example.com", email_type="other", verified=True)
        url = reverse("admin:authn_contactemail_change", args=[unlinked.pk])
        data = scrape_admin_form(self.client, url)
        data.pop("verified", None)

        page = self.confirmation(url, data)

        self.assertNotContains(page, "Warning: signing in")

    def test_adding_an_address_never_warns(self):
        url = reverse("admin:authn_contactemail_add")
        data = scrape_admin_form(
            self.client,
            url,
            {"member": str(self.jane.pk), "email_address": "jane.new@example.com", "email_type": "other"},
        )

        page = self.confirmation(url, data)

        self.assertContains(page, "jane.new@example.com")
        self.assertNotContains(page, "Warning: signing in")

    def test_other_contact_edits_do_not_warn(self):
        url = reverse("admin:authn_contactemail_change", args=[self.jane_primary.pk])
        data = scrape_admin_form(self.client, url)
        data.pop("subscribe", None)

        page = self.confirmation(url, data)

        self.assertNotContains(page, "Warning: signing in")
