"""Unverifying (or removing) a member's last verified email or phone is allowed, with a warning before and after."""

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.admin.members.sign_in_warning import MAX_NAMED, member_page_row, warning_text
from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.helpers import scrape_admin_form

Member = get_user_model()

EMAILS = reverse("admin:authn_contactemail_changelist")
PHONES = reverse("admin:authn_contactphone_changelist")
LOCKED_OUT = "now has no verified email address or phone number, so they cannot sign in until one is verified"


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def warned(response) -> bool:
    return any("no verified email address or phone number" in text for text in texts(response))


class WarningFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.master = Member.objects.create_superuser(password="StrongPass123!", first_name="Ada", last_name="Master")
        ContactEmail.objects.create(member=cls.master, email_address="master@example.com", verified=True)
        cls.jane = Member.objects.create_user(first_name="Jane", last_name="Doe", is_active=True)
        cls.jane_primary = ContactEmail.objects.create(
            member=cls.jane, email_address="jane@example.com", email_type="primary", verified=True
        )
        cls.pat = Member.objects.create_user(first_name="Pat", last_name="Phone", is_active=True)
        cls.pat_phone = ContactPhone.objects.create(member=cls.pat, phone_number="2095550120", verified=True)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.master)

    def tearDown(self):
        cache.clear()

    def member_url(self, member):
        return reverse("admin:authn_member_change", args=[member.pk])

    def member_page(self, member, *, untick=(), delete=(), overrides=None):
        """The member page as rendered, with Verified unticked / DELETE ticked on the given contact rows."""
        data = scrape_admin_form(self.client, self.member_url(member), overrides)
        for prefix in ("contact_emails", "contact_phones"):
            for index in range(int(data[f"{prefix}-TOTAL_FORMS"])):
                row = data.get(f"{prefix}-{index}-id")
                if row in {str(item.pk) for item in untick}:
                    data.pop(f"{prefix}-{index}-verified", None)
                if row in {str(item.pk) for item in delete}:
                    data[f"{prefix}-{index}-DELETE"] = "on"
        return data


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MemberPageWarningTests(WarningFixture):
    def test_unticking_the_last_verified_email_warns_but_saves(self):
        response = self.client.post(
            self.member_url(self.jane), self.member_page(self.jane, untick=[self.jane_primary]), follow=True
        )

        self.assertFalse(ContactEmail.objects.get(pk=self.jane_primary.pk).verified)
        self.assertTrue(any(f"Jane Doe {LOCKED_OUT}" in text for text in texts(response)), texts(response))

    def test_no_warning_while_another_verified_contact_remains(self):
        ContactPhone.objects.create(member=self.jane, phone_number="2095550121", verified=True)

        response = self.client.post(
            self.member_url(self.jane), self.member_page(self.jane, untick=[self.jane_primary]), follow=True
        )

        self.assertFalse(ContactEmail.objects.get(pk=self.jane_primary.pk).verified)
        self.assertFalse(warned(response))

    def test_no_warning_when_the_member_already_had_none(self):
        ContactEmail.objects.filter(pk=self.jane_primary.pk).update(verified=False)

        response = self.client.post(self.member_url(self.jane), self.member_page(self.jane), follow=True)

        self.assertFalse(warned(response))

    def test_removing_the_last_verified_row_warns(self):
        ContactEmail.objects.filter(pk=self.jane_primary.pk).update(verified=False)
        backup = ContactEmail.objects.create(
            member=self.jane, email_address="jane.work@example.com", email_type="secondary", verified=True
        )

        response = self.client.post(
            self.member_url(self.jane), self.member_page(self.jane, delete=[backup]), follow=True
        )

        self.assertFalse(ContactEmail.objects.filter(pk=backup.pk).exists())
        self.assertTrue(warned(response))

    def test_unticking_a_phone_only_members_number_warns(self):
        response = self.client.post(
            self.member_url(self.pat), self.member_page(self.pat, untick=[self.pat_phone]), follow=True
        )

        self.assertFalse(ContactPhone.objects.get(pk=self.pat_phone.pk).verified)
        self.assertTrue(any(f"Pat Phone {LOCKED_OUT}" in text for text in texts(response)))


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
