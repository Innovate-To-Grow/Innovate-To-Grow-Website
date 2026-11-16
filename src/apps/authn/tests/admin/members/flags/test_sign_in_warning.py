"""Unverifying (or removing) a member's last verified email or phone is allowed, with a warning before and after."""

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.helpers import scrape_admin_form

Member = get_user_model()

EMAILS = reverse("admin:authn_contactemail_changelist")
PHONES = reverse("admin:authn_contactphone_changelist")
LOCKED_OUT = (
    "now has no verified email address or phone number, so they cannot sign in with a code or a password until one is "
    "verified (only a personal sign-in link from an email they received still works, until it expires)"
)


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
