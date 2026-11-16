"""The Members list and every member picker find the member searched for, first, with no phone decoys.

Stefano's report (2026-11): searching a member's exact address, which had "32" in it, listed 20 members who do not
match, and searching the part before the @ of another address (with "28") was wrong too. The member search stripped
every non-digit from the *whole* term and also matched what was left against phone numbers, so "32" and "28" pulled in
every member whose phone contains them. The member pickers (autocomplete, 20 per page) then filled with those newer
decoys and never showed the real member. The members here are made up, with addresses of the same shape.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone

Member = get_user_model()

CHANGELIST = reverse("admin:authn_member_changelist")
AUTOCOMPLETE = reverse("admin:autocomplete")
# Every model whose ``member`` field is a member picker (``autocomplete_fields = ["member"]``).
MEMBER_PICKERS = (
    ("authn", "contactemail"),
    ("authn", "contactphone"),
    ("event", "eventregistration"),
)
DECOYS_PER_NUMBER = 25  # more than the pickers' page of 20


def _joined(year, month=1, day=1):
    return timezone.make_aware(datetime.datetime(year, month, day, 12, 0))


def _member(first, last, email, *, joined, phone=None, **extra):
    member = Member.objects.create_user(first_name=first, last_name=last, is_active=True, **extra)
    Member.objects.filter(pk=member.pk).update(date_joined=joined)
    ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
    if phone:
        ContactPhone.objects.create(member=member, phone_number=phone, region="1-US")
    member.refresh_from_db()
    return member


class _SearchFixture(TestCase):
    """Made-up members shaped like the reported ones, and 50 newer decoys whose phones contain "32" or "28"."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = Member.objects.create_superuser(password="StrongPass123!", first_name="Admin", last_name="User")
        ContactEmail.objects.create(
            member=cls.superuser, email_address="admin@example.com", email_type="primary", verified=True
        )
        # Oldest first, so the list's usual order (newest first) puts each of them last.
        cls.ana = _member("Ana", "Quill", "aquill32@example.edu", joined=_joined(2020, 1), phone="2097654100")
        cls.brian = _member("Brian", "Fenwick", "bfenwick28@example.edu", joined=_joined(2020, 2))
        cls.bob = _member("Bob", "Fenwick", "bfenwick@example.edu", joined=_joined(2020, 3))
        cls.bea = _member("Bea", "Fenwickson", "bfenwick281@example.net", joined=_joined(2020, 4))
        cls.decoys = cls._make_decoys()

    @classmethod
    def _make_decoys(cls):
        letters = "kmpqtvwxyz"
        decoys = []
        for index in range(2 * DECOYS_PER_NUMBER):
            area_digits = "32" if index % 2 == 0 else "28"
            suffix = letters[index // 10] + letters[index % 10]
            decoys.append(
                _member(
                    "Decoy",
                    f"Number {suffix}",
                    f"decoy.{suffix}@example.org",
                    joined=_joined(2026, 1) + datetime.timedelta(days=index),
                    phone=f"209{area_digits}{index:05d}",
                )
            )
        return decoys

    def setUp(self):
        cache.clear()
        self.client.force_login(self.superuser)

    def tearDown(self):
        cache.clear()

    def changelist(self, term, *, all_pages=False, **params):
        response = self.client.get(CHANGELIST, {"q": term, **params})
        self.assertEqual(response.status_code, 200)
        changelist = response.context["cl"]
        return list(changelist.queryset if all_pages else changelist.result_list)

    def picker(self, term, app_label="authn", model_name="contactemail"):
        response = self.client.get(
            AUTOCOMPLETE,
            {"term": term, "app_label": app_label, "model_name": model_name, "field_name": "member"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        return [row["id"] for row in payload["results"]], payload["pagination"]["more"]

    def assert_no_decoys(self, members):
        self.assertFalse({member.pk for member in self.decoys} & {member.pk for member in members})


class MemberChangelistExactSearchTests(_SearchFixture):
    def test_exact_email_lists_only_that_member(self):
        self.assertEqual(self.changelist("aquill32@example.edu"), [self.ana])

    def test_exact_email_ignores_letter_case(self):
        self.assertEqual(self.changelist("AQuill32@Example.EDU"), [self.ana])

    def test_handle_lists_the_exact_handle_first_and_no_decoys(self):
        # Bea (bfenwick281@) is newer, so without the rank she would be listed first.
        self.assertEqual(self.changelist("bfenwick28"), [self.brian, self.bea])

    def test_handle_with_trailing_at_matches_that_handle_only(self):
        self.assertEqual(self.changelist("bfenwick28@"), [self.brian])

    def test_shorter_handle_puts_its_own_address_first(self):
        self.assertEqual(self.changelist("bfenwick"), [self.bob, self.bea, self.brian])

    def test_quoted_email_is_still_exact(self):
        self.assertEqual(self.changelist('"aquill32@example.edu"'), [self.ana])

    def test_exact_email_ranks_above_a_newer_address_that_contains_it(self):
        axel = _member("Axel", "Quill", "xaquill32@example.edu", joined=_joined(2025, 6))
        self.assertEqual(self.changelist("aquill32@example.edu"), [self.ana, axel])

    def test_secondary_address_counts_as_an_exact_match(self):
        ContactEmail.objects.create(member=self.bob, email_address="bob.fenwick@example.net", email_type="secondary")
        self.assertEqual(self.changelist("bob.fenwick@example.net"), [self.bob])

    def test_unknown_email_lists_nobody(self):
        self.assertEqual(self.changelist("jdoe2@example.edu"), [])

    def test_explicit_column_sort_wins_over_the_rank(self):
        column = self._column("date_joined")
        self.assertEqual(self.changelist("bfenwick28", o=f"-{column}"), [self.bea, self.brian])
        self.assertEqual(self.changelist("bfenwick28", o=str(column)), [self.brian, self.bea])

    def test_list_filters_still_apply(self):
        Member.objects.filter(pk=self.brian.pk).update(is_active=False)
        self.assertEqual(self.changelist("bfenwick28", is_active__exact="1"), [self.bea])
        self.assertEqual(self.changelist("(209) 765-4100", is_active__exact="0"), [])

    def test_facet_counts_render_with_a_ranked_search(self):
        self.assertEqual(self.changelist("bfenwick28", _facets="1"), [self.brian, self.bea])

    def test_search_box_says_what_it_searches(self):
        self.assertContains(self.client.get(CHANGELIST), 'placeholder="Email, name, phone, organization or UUID"')

    def _column(self, name):
        response = self.client.get(CHANGELIST)
        return response.context["cl"].list_display.index(name)
