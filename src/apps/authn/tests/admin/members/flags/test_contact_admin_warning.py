from django.test import override_settings
from django.urls import reverse

from apps.authn.admin.members.shared.sign_in_warning import MAX_NAMED, member_page_row, warning_text
from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.admin.members.flags.test_sign_in_warning import (
    EMAILS,
    LOCKED_OUT,
    PHONES,
    Member,
    WarningFixture,
    texts,
    warned,
)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ContactAdminWarningTests(WarningFixture):
    def run_action(self, url, action, rows):
        data = {"action": action, "_selected_action": [str(row.pk) for row in rows], "select_across": "0", "index": "0"}
        return self.client.post(url, data, follow=True)

    def test_the_bulk_email_action_names_the_members_it_locks_out(self):
        ContactEmail.objects.create(member=self.pat, email_address="pat@example.com", verified=True)
        ContactPhone.objects.filter(pk=self.pat_phone.pk).update(verified=False)
        rows = ContactEmail.objects.filter(member__in=[self.jane, self.pat])

        response = self.run_action(EMAILS, "mark_unverified", rows)

        self.assertFalse(ContactEmail.objects.filter(member__in=[self.jane, self.pat], verified=True).exists())
        self.assertTrue(
            any(
                "2 members now have no verified email address or phone number (Jane Doe, Pat Phone)" in text
                for text in texts(response)
            ),
            texts(response),
        )

    def test_the_bulk_phone_action_warns(self):
        response = self.run_action(PHONES, "mark_unverified", [self.pat_phone])

        self.assertFalse(ContactPhone.objects.get(pk=self.pat_phone.pk).verified)
        self.assertTrue(any(f"Pat Phone {LOCKED_OUT}" in text for text in texts(response)))

    def test_the_list_editable_column_warns(self):
        response = self.client.get(f"{EMAILS}?q=jane@example.com")
        self.assertEqual([row.pk for row in response.context["cl"].result_list], [self.jane_primary.pk])
        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-0-id": str(self.jane_primary.pk),
            "form-0-subscribe": "on",
            "_save": "Save",
        }

        response = self.client.post(f"{EMAILS}?q=jane@example.com", data, follow=True)

        self.assertFalse(ContactEmail.objects.get(pk=self.jane_primary.pk).verified)
        self.assertTrue(warned(response))

    def test_deleting_the_last_verified_address_warns(self):
        ContactEmail.objects.filter(pk=self.jane_primary.pk).update(verified=False)
        backup = ContactEmail.objects.create(
            member=self.jane, email_address="jane.work@example.com", email_type="secondary", verified=True
        )

        response = self.client.post(
            reverse("admin:authn_contactemail_delete", args=[backup.pk]), {"post": "yes"}, follow=True
        )

        self.assertFalse(ContactEmail.objects.filter(pk=backup.pk).exists())
        self.assertTrue(warned(response))

    def test_bulk_deleting_phones_warns(self):
        response = self.run_action(PHONES, "delete_selected", [self.pat_phone])
        self.assertEqual(response.status_code, 200)  # Django's "are you sure?" page

        response = self.client.post(
            PHONES,
            {"action": "delete_selected", "_selected_action": [str(self.pat_phone.pk)], "post": "yes"},
            follow=True,
        )

        self.assertFalse(ContactPhone.objects.filter(pk=self.pat_phone.pk).exists())
        self.assertTrue(warned(response))

    def test_bulk_deleting_emails_warns(self):
        ContactEmail.objects.filter(pk=self.jane_primary.pk).update(verified=False)
        backup = ContactEmail.objects.create(
            member=self.jane, email_address="jane.work@example.com", email_type="secondary", verified=True
        )

        response = self.client.post(
            EMAILS, {"action": "delete_selected", "_selected_action": [str(backup.pk)], "post": "yes"}, follow=True
        )

        self.assertFalse(ContactEmail.objects.filter(pk=backup.pk).exists())
        self.assertTrue(warned(response))

    def test_making_an_unlinked_address_primary_is_refused(self):
        unlinked = ContactEmail.objects.create(email_address="nobody@example.com", email_type="other", verified=True)

        response = self.run_action(EMAILS, "make_primary", [unlinked])

        self.assertIn("The selected email must belong to a member.", texts(response))
        self.assertEqual(ContactEmail.objects.get(pk=unlinked.pk).email_type, "other")

    def test_marking_an_already_unverified_address_says_nothing_more(self):
        ContactEmail.objects.filter(pk=self.jane_primary.pk).update(verified=False)

        response = self.run_action(EMAILS, "mark_unverified", [self.jane_primary])

        self.assertFalse(warned(response))


class WarningTextTests(WarningFixture):
    def test_long_lists_are_cut_short(self):
        members = [
            Member.objects.create_user(first_name=f"Person{index}", last_name="Example")
            for index in range(MAX_NAMED + 2)
        ]

        text = warning_text({member.pk for member in members})

        self.assertIn(f"{MAX_NAMED + 2} members now have", text)
        self.assertIn("and 2 more", text)

    def test_a_page_without_contact_rows_counts_what_is_stored(self):
        self.assertIsNone(member_page_row(self.jane, []))
        self.assertIsNone(member_page_row(None, []))
        ContactEmail.objects.filter(member=self.jane).update(verified=False)
        self.assertIsNone(member_page_row(self.jane, []))  # had none before either
