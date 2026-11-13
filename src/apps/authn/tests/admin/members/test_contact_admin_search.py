"""Contact Emails and Contact Phones searches: exact matches first, and formatted phone numbers are found."""

import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone

Member = get_user_model()

EMAILS = reverse("admin:authn_contactemail_changelist")
PHONES = reverse("admin:authn_contactphone_changelist")


class _ContactFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = Member.objects.create_superuser(password="StrongPass123!", first_name="Admin", last_name="User")
        ContactEmail.objects.create(
            member=cls.superuser, email_address="admin@example.com", email_type="primary", verified=True
        )
        cls.ana = Member.objects.create_user(first_name="Ana", last_name="Quill", is_active=True)
        cls.brian = Member.objects.create_user(first_name="Brian", last_name="Fenwick", is_active=True)
        cls.bob = Member.objects.create_user(first_name="Bob", last_name="Fenwick", is_active=True)
        cls.bea = Member.objects.create_user(first_name="Bea", last_name="Fenwickson", is_active=True)
        # Created oldest first, so the lists' usual order (newest first) puts the exact match last.
        cls.ana_email = cls._email(cls.ana, "aquill32@example.edu", days_ago=40)
        cls.brian_email = cls._email(cls.brian, "bfenwick28@example.edu", days_ago=30)
        cls.bob_email = cls._email(cls.bob, "bfenwick@example.edu", days_ago=20)
        cls.bea_email = cls._email(cls.bea, "bfenwick281@example.net", days_ago=10)
        cls.unlinked = cls._email(None, "aquill32@example.edu.example", days_ago=5, email_type="other")
        cls.ana_phone = cls._phone(cls.ana, "2097654100", days_ago=40)
        # A row saved before numbers were normalized, with the country code still in front.
        cls.legacy_phone = cls._phone(cls.bob, "12097654100", days_ago=20)
        cls.bea_phone = cls._phone(cls.bea, "2093228000", days_ago=10)

    @staticmethod
    def _email(member, address, *, days_ago, email_type="primary"):
        row = ContactEmail.objects.create(member=member, email_address=address, email_type=email_type)
        ContactEmail.objects.filter(pk=row.pk).update(created_at=timezone.now() - datetime.timedelta(days=days_ago))
        return row

    @staticmethod
    def _phone(member, number, *, days_ago):
        row = ContactPhone.objects.create(member=member, phone_number=number, region="1-US")
        ContactPhone.objects.filter(pk=row.pk).update(created_at=timezone.now() - datetime.timedelta(days=days_ago))
        return row

    def setUp(self):
        cache.clear()
        self.client.force_login(self.superuser)

    def tearDown(self):
        cache.clear()

    def search(self, url, term, **params):
        response = self.client.get(url, {"q": term, **params})
        self.assertEqual(response.status_code, 200)
        return [row.pk for row in response.context["cl"].result_list]

    def column(self, url, name):
        return self.client.get(url).context["cl"].list_display.index(name)


class ContactEmailSearchTests(_ContactFixture):
    def test_exact_address_comes_first(self):
        self.assertEqual(self.search(EMAILS, "aquill32@example.edu"), [self.ana_email.pk, self.unlinked.pk])

    def test_exact_address_ignores_letter_case(self):
        self.assertEqual(self.search(EMAILS, "BFENWICK28@EXAMPLE.EDU"), [self.brian_email.pk])

    def test_handle_puts_its_own_address_first(self):
        self.assertEqual(self.search(EMAILS, "bfenwick28"), [self.brian_email.pk, self.bea_email.pk])
        self.assertEqual(self.search(EMAILS, "bfenwick"), [self.bob_email.pk, self.bea_email.pk, self.brian_email.pk])

    def test_partial_address_with_at_ranks_addresses_starting_with_it(self):
        self.assertEqual(self.search(EMAILS, "bfenwick28@example"), [self.brian_email.pk])

    def test_member_name_search_is_unchanged(self):
        self.assertEqual(self.search(EMAILS, "Fenwickson"), [self.bea_email.pk])
        self.assertEqual(self.search(EMAILS, "Brian Fenwick"), [self.brian_email.pk])

    def test_digits_never_match_phone_numbers_here(self):
        self.assertEqual(self.search(EMAILS, "2097654100"), [])

    def test_explicit_column_sort_wins_over_the_rank(self):
        column = self.column(EMAILS, "created_at")
        self.assertEqual(self.search(EMAILS, "bfenwick28", o=f"-{column}"), [self.bea_email.pk, self.brian_email.pk])

    def test_search_box_says_what_it_searches(self):
        self.assertContains(self.client.get(EMAILS), 'placeholder="Email address or member name"')

    def test_actions_run_on_ranked_search_results(self):
        # "Make selected email primary" counts and reads the selection from the ranked results.
        ContactEmail.objects.filter(pk=self.brian_email.pk).update(email_type="secondary", verified=True)
        selection = {"_selected_action": [str(self.brian_email.pk)], "select_across": "0", "index": "0"}
        with self.settings(ADMIN_REQUIRE_CONFIRMATION=False):
            response = self.client.post(f"{EMAILS}?q=bfenwick28", {"action": "make_primary", **selection})
        self.assertEqual(response.status_code, 302)
        self.brian_email.refresh_from_db()
        self.assertEqual(self.brian_email.email_type, "primary")


class ContactPhoneSearchTests(_ContactFixture):
    def test_formatted_numbers_are_found(self):
        for term in (
            "2097654100",
            "(209) 765-4100",
            "209-765-4100",
            "209.765.4100",
            "209 765 4100",
            "+1 209 765 4100",
            "+12097654100",
            "1 (209) 765-4100",
        ):
            with self.subTest(term=term):
                self.assertEqual(self.search(PHONES, term), [self.ana_phone.pk, self.legacy_phone.pk])

    def test_partial_numbers_are_found(self):
        self.assertEqual(self.search(PHONES, "765-4100"), [self.legacy_phone.pk, self.ana_phone.pk])
        self.assertEqual(self.search(PHONES, "(322)"), [self.bea_phone.pk])

    def test_too_few_digits_and_letters_are_not_phone_searches(self):
        self.assertEqual(self.search(PHONES, "(20)"), [])
        self.assertEqual(self.search(PHONES, "aquill32@example.edu"), [])

    def test_member_name_search_is_unchanged(self):
        self.assertEqual(self.search(PHONES, "Quill"), [self.ana_phone.pk])
        self.assertEqual(self.search(PHONES, "Fenwick"), [self.bea_phone.pk, self.legacy_phone.pk])

    def test_explicit_column_sort_wins_over_the_rank(self):
        column = self.column(PHONES, "created_at")
        self.assertEqual(self.search(PHONES, "2097654100", o=f"-{column}"), [self.legacy_phone.pk, self.ana_phone.pk])

    def test_search_box_says_what_it_searches(self):
        self.assertContains(self.client.get(PHONES), 'placeholder="Phone number or member name"')
