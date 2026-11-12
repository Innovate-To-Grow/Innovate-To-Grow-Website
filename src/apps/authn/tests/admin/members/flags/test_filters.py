"""The Members, Contact Emails and Contact Phones filters keep the account flag apart from the address flags."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone

Member = get_user_model()

MEMBERS = reverse("admin:authn_member_changelist")
EMAILS = reverse("admin:authn_contactemail_changelist")
PHONES = reverse("admin:authn_contactphone_changelist")


def email(member, address, email_type, *, verified=True, subscribe=True):
    return ContactEmail.objects.create(
        member=member, email_address=address, email_type=email_type, verified=verified, subscribe=subscribe
    )


class FilterFixture(TestCase):
    """Made-up members, one per combination the filters tell apart."""

    @classmethod
    def setUpTestData(cls):
        cls.master = Member.objects.create_superuser(password="StrongPass123!", first_name="Ada", last_name="Master")
        email(cls.master, "master@example.com", "primary")
        # Active; verified + subscribed primary; an unverified secondary; a verified phone.
        cls.ana = Member.objects.create_user(first_name="Ana", last_name="Active", is_active=True)
        email(cls.ana, "ana@example.com", "primary")
        email(cls.ana, "ana.alt@example.com", "secondary", verified=False, subscribe=False)
        ContactPhone.objects.create(member=cls.ana, phone_number="2095550101", verified=True)
        # Deactivated; unverified, unsubscribed primary.
        cls.ivan = Member.objects.create_user(first_name="Ivan", last_name="Inactive", is_active=False)
        email(cls.ivan, "ivan@example.com", "primary", verified=False, subscribe=False)
        # An unfinished self-service sign-up.
        cls.pete = Member.objects.create_user(
            first_name="Pete", last_name="Pending", is_active=False, registration_pending=True
        )
        email(cls.pete, "pete@example.com", "primary", verified=False)
        # Active, no primary (a legacy gap); a verified, subscribed secondary; an unverified phone.
        cls.leo = Member.objects.create_user(first_name="Leo", last_name="Legacy", is_active=True)
        email(cls.leo, "leo@example.com", "secondary")
        ContactPhone.objects.create(member=cls.leo, phone_number="2095550102", verified=False)
        # Active; unsubscribed primary, subscribed secondary.
        cls.sue = Member.objects.create_user(first_name="Sue", last_name="Secondary", is_active=True)
        email(cls.sue, "sue@example.com", "primary", subscribe=False)
        email(cls.sue, "sue.alt@example.com", "secondary")
        # Phone-only.
        cls.pat = Member.objects.create_user(first_name="Pat", last_name="Phone", is_active=True)
        ContactPhone.objects.create(member=cls.pat, phone_number="2095550103", verified=True)
        cls.staffer = Member.objects.create_user(first_name="Sam", last_name="Staff", is_active=True, is_staff=True)
        email(cls.staffer, "sam@example.com", "primary")
        email(None, "nobody@example.com", "other", verified=False)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.master)

    def tearDown(self):
        cache.clear()

    def names(self, url, query) -> set:
        response = self.client.get(f"{url}?{query}")
        self.assertEqual(response.status_code, 200, query)
        return {str(row) if url == MEMBERS else self.label(row) for row in response.context["cl"].result_list}

    @staticmethod
    def label(row) -> str:
        return getattr(row, "email_address", None) or row.phone_number


class MemberFilterTests(FilterFixture):
    def test_account_active(self):
        everyone_active = {"Ada Master", "Ana Active", "Leo Legacy", "Sue Secondary", "Pat Phone", "Sam Staff"}
        self.assertEqual(self.names(MEMBERS, "account=active"), everyone_active)
        self.assertEqual(self.names(MEMBERS, "account=inactive"), {"Ivan Inactive", "Pete Pending"})
        self.assertEqual(self.names(MEMBERS, "account=pending"), {"Pete Pending"})

    def test_primary_email(self):
        self.assertEqual(
            self.names(MEMBERS, "primary_email=verified"), {"Ada Master", "Ana Active", "Sue Secondary", "Sam Staff"}
        )
        self.assertEqual(self.names(MEMBERS, "primary_email=unverified"), {"Ivan Inactive", "Pete Pending"})
        self.assertEqual(self.names(MEMBERS, "primary_email=none"), {"Leo Legacy", "Pat Phone"})

    def test_unverified_emails(self):
        self.assertEqual(self.names(MEMBERS, "unverified_email=yes"), {"Ana Active", "Ivan Inactive", "Pete Pending"})
        self.assertEqual(
            self.names(MEMBERS, "unverified_email=no"),
            {"Ada Master", "Leo Legacy", "Sue Secondary", "Pat Phone", "Sam Staff"},
        )

    def test_newsletter(self):
        self.assertEqual(
            self.names(MEMBERS, "newsletter=primary"), {"Ada Master", "Ana Active", "Pete Pending", "Sam Staff"}
        )
        self.assertEqual(self.names(MEMBERS, "newsletter=other_only"), {"Leo Legacy", "Sue Secondary"})
        self.assertEqual(self.names(MEMBERS, "newsletter=none"), {"Ivan Inactive", "Pat Phone"})

    def test_phone(self):
        self.assertEqual(self.names(MEMBERS, "phone=verified"), {"Ana Active", "Pat Phone"})
        self.assertEqual(self.names(MEMBERS, "phone=unverified"), {"Leo Legacy"})
        self.assertEqual(
            self.names(MEMBERS, "phone=none"),
            {"Ada Master", "Ivan Inactive", "Pete Pending", "Sue Secondary", "Sam Staff"},
        )

    def test_filters_combine_and_never_duplicate_a_member(self):
        self.assertEqual(self.names(MEMBERS, "account=active&newsletter=other_only&phone=unverified"), {"Leo Legacy"})
        response = self.client.get(f"{MEMBERS}?unverified_email=yes")
        members = list(response.context["cl"].result_list)
        self.assertEqual(len(members), len({member.pk for member in members}))

    def test_the_list_names_the_filters_and_the_account_column(self):
        response = self.client.get(MEMBERS)

        for title in ("Account active", "Primary email", "Unverified emails", "Newsletter (All subscribers)", "Phone"):
            with self.subTest(title=title):
                self.assertContains(response, title)
        self.assertContains(response, "Unfinished sign-up")
        self.assertIn("account_active", response.context["cl"].list_display)


class ContactFilterTests(FilterFixture):
    def test_verified(self):
        unverified = {"ana.alt@example.com", "ivan@example.com", "pete@example.com", "nobody@example.com"}
        self.assertEqual(self.names(EMAILS, "verified_status=unverified"), unverified)
        self.assertNotIn("ana.alt@example.com", self.names(EMAILS, "verified_status=verified"))
        self.assertIn("leo@example.com", self.names(EMAILS, "verified_status=verified"))
        # An unlinked row is nobody's primary.
        self.assertEqual(
            self.names(EMAILS, "verified_status=unverified_primary"), {"ivan@example.com", "pete@example.com"}
        )

    def test_subscribed(self):
        self.assertEqual(
            self.names(EMAILS, "subscribed=no"), {"ana.alt@example.com", "ivan@example.com", "sue@example.com"}
        )
        self.assertIn("sue.alt@example.com", self.names(EMAILS, "subscribed=yes"))

    def test_member_account(self):
        self.assertEqual(self.names(EMAILS, "account=inactive"), {"ivan@example.com", "pete@example.com"})
        self.assertEqual(self.names(EMAILS, "account=staff"), {"master@example.com", "sam@example.com"})
        self.assertEqual(self.names(EMAILS, "account=unlinked"), {"nobody@example.com"})
        self.assertNotIn("nobody@example.com", self.names(EMAILS, "account=active"))
        self.assertIn("leo@example.com", self.names(EMAILS, "account=active"))

    def test_links_to_the_old_yes_no_filters_still_work(self):
        self.assertEqual(self.names(EMAILS, "verified__exact=0"), self.names(EMAILS, "verified_status=unverified"))
        self.assertEqual(self.names(EMAILS, "subscribe__exact=0"), self.names(EMAILS, "subscribed=no"))

    def test_email_type_still_filters(self):
        self.assertIn("sue.alt@example.com", self.names(EMAILS, "email_type__exact=secondary"))
        self.assertNotIn("sue@example.com", self.names(EMAILS, "email_type__exact=secondary"))

    def test_phones_by_member_account(self):
        self.assertEqual(self.names(PHONES, "account=active"), {"2095550101", "2095550102", "2095550103"})
        self.assertEqual(self.names(PHONES, "account=inactive"), set())

    def test_the_lists_name_the_filters(self):
        response = self.client.get(EMAILS)
        for title in ("Verified (sign-in)", "Unverified emails", "Subscribed (newsletters)", "Member account"):
            with self.subTest(title=title):
                self.assertContains(response, title)
        self.assertContains(self.client.get(PHONES), "Member account")
