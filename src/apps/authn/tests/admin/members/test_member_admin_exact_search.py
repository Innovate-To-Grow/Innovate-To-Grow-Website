"""The Members list and every member picker find the member searched for, first, with no phone decoys.

Stefano's report (2026-11): searching ``acalderon32@ucmerced.edu`` in the member admin listed 20 members who do not
match, and ``blewis28`` was wrong too. The member search stripped every non-digit from the *whole* term and also
matched what was left against phone numbers, so "32" and "28" pulled in every member whose phone contains them. The
member pickers (autocomplete, 20 per page) then filled with those newer decoys and never showed the real member.
"""

import datetime

from django.contrib.admin import ModelAdmin
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import F
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.admin.members.member import MemberAdmin
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
    """The members from the report, and 50 newer decoys whose phone numbers contain "32" or "28"."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = Member.objects.create_superuser(password="StrongPass123!", first_name="Admin", last_name="User")
        ContactEmail.objects.create(
            member=cls.superuser, email_address="admin@example.com", email_type="primary", verified=True
        )
        # Oldest first, so the list's usual order (newest first) puts each of them last.
        cls.ana = _member("Ana", "Calderon", "acalderon32@ucmerced.edu", joined=_joined(2020, 1), phone="2097654100")
        cls.brian = _member("Brian", "Lewis", "blewis28@ucmerced.edu", joined=_joined(2020, 2))
        cls.bob = _member("Bob", "Lewis", "blewis@ucmerced.edu", joined=_joined(2020, 3))
        cls.bea = _member("Bea", "Lewiston", "blewis281@gmail.com", joined=_joined(2020, 4))
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
        self.assertEqual(self.changelist("acalderon32@ucmerced.edu"), [self.ana])

    def test_exact_email_ignores_letter_case(self):
        self.assertEqual(self.changelist("ACalderon32@UCMerced.EDU"), [self.ana])

    def test_handle_lists_the_exact_handle_first_and_no_decoys(self):
        # Bea (blewis281@) is newer, so without the rank she would be listed first.
        self.assertEqual(self.changelist("blewis28"), [self.brian, self.bea])

    def test_handle_with_trailing_at_matches_that_handle_only(self):
        self.assertEqual(self.changelist("blewis28@"), [self.brian])

    def test_shorter_handle_puts_its_own_address_first(self):
        self.assertEqual(self.changelist("blewis"), [self.bob, self.bea, self.brian])

    def test_quoted_email_is_still_exact(self):
        self.assertEqual(self.changelist('"acalderon32@ucmerced.edu"'), [self.ana])

    def test_exact_email_ranks_above_a_newer_address_that_contains_it(self):
        axel = _member("Axel", "Calderon", "xacalderon32@ucmerced.edu", joined=_joined(2025, 6))
        self.assertEqual(self.changelist("acalderon32@ucmerced.edu"), [self.ana, axel])

    def test_secondary_address_counts_as_an_exact_match(self):
        ContactEmail.objects.create(member=self.bob, email_address="bob.lewis@gmail.com", email_type="secondary")
        self.assertEqual(self.changelist("bob.lewis@gmail.com"), [self.bob])

    def test_unknown_email_lists_nobody(self):
        self.assertEqual(self.changelist("jdoe2@ucmerced.edu"), [])

    def test_explicit_column_sort_wins_over_the_rank(self):
        column = self._column("date_joined")
        self.assertEqual(self.changelist("blewis28", o=f"-{column}"), [self.bea, self.brian])
        self.assertEqual(self.changelist("blewis28", o=str(column)), [self.brian, self.bea])

    def test_list_filters_still_apply(self):
        Member.objects.filter(pk=self.brian.pk).update(is_active=False)
        self.assertEqual(self.changelist("blewis28", is_active__exact="1"), [self.bea])
        self.assertEqual(self.changelist("(209) 765-4100", is_active__exact="0"), [])

    def test_facet_counts_render_with_a_ranked_search(self):
        self.assertEqual(self.changelist("blewis28", _facets="1"), [self.brian, self.bea])

    def test_search_box_says_what_it_searches(self):
        self.assertContains(self.client.get(CHANGELIST), 'placeholder="Email, name, phone, organization or UUID"')

    def _column(self, name):
        response = self.client.get(CHANGELIST)
        return response.context["cl"].list_display.index(name)


class MemberChangelistPhoneSearchTests(_SearchFixture):
    """Phone searches that worked before keep working; only phone-shaped terms reach phone numbers."""

    def test_full_number_in_every_common_format_finds_the_member_first(self):
        for term in (
            "2097654100",
            "(209) 765-4100",
            "(209)765-4100",
            "209-765-4100",
            "209.765.4100",
            "209 765 4100",
            "+1 209 765 4100",
            "+1 (209) 765-4100",
            "+12097654100",
            "12097654100",
            "1-209-765-4100",
        ):
            with self.subTest(term=term):
                results = self.changelist(term)
                self.assertEqual(results[0], self.ana)
                self.assert_no_decoys(results)

    def test_partial_numbers_still_match(self):
        for term in ("7654100", "765-4100", "765 4100"):
            with self.subTest(term=term):
                self.assertIn(self.ana, self.changelist(term))

    def test_area_code_search_still_lists_every_matching_number(self):
        results = self.changelist("209", all_pages=True)
        self.assertIn(self.ana, results)
        self.assertLessEqual(set(self.decoys), set(results))

    def test_three_digits_are_enough_and_two_are_not(self):
        self.assertEqual(self.changelist("(765)"), [self.ana])
        self.assertEqual(self.changelist("(76)"), [])

    def test_formatted_partial_number_matches_only_numbers_containing_its_digits(self):
        results = self.changelist("(209) 32", all_pages=True)
        self.assertEqual(set(results), {decoy for index, decoy in enumerate(self.decoys) if index % 2 == 0})

    def test_name_with_digits_is_not_a_phone_search(self):
        results = self.changelist("Ana 209")
        self.assert_no_decoys(results)
        self.assertLessEqual(set(results), {self.ana})

    def test_two_words_match_name_parts(self):
        self.assertEqual(self.changelist("Ana Calderon"), [self.ana])
        self.assertEqual(self.changelist("Lewis Brian"), [self.brian])
        self.assertEqual(self.changelist("lewis"), [self.bea, self.bob, self.brian])


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MemberChangelistActionsOnSearchResultsTests(_SearchFixture):
    """Select-all actions run on the ranked search results (annotated, de-duplicated) without errors."""

    def _post(self, action, term):
        return self.client.post(
            f"{CHANGELIST}?q={term}",
            {"action": action, "_selected_action": [str(self.brian.pk)], "select_across": "1", "index": "0"},
        )

    def test_vcard_export_of_all_search_results(self):
        response = self._post("export_members_to_vcard", "blewis28")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("FN:Brian Lewis", body)
        self.assertIn("FN:Bea Lewiston", body)
        self.assertEqual(body.count("BEGIN:VCARD"), 2)

    def test_deactivate_all_search_results(self):
        response = self._post("deactivate_members", "blewis28")
        self.assertEqual(response.status_code, 302)
        inactive = set(Member.objects.filter(is_active=False).values_list("pk", flat=True))
        self.assertEqual(inactive, {self.brian.pk, self.bea.pk})


class MemberPickerExactSearchTests(_SearchFixture):
    """Every member picker (autocomplete) runs the member search: the member is on the first page, first."""

    def test_exact_email_returns_only_that_member_in_every_picker(self):
        for app_label, model_name in MEMBER_PICKERS:
            with self.subTest(picker=model_name):
                self.assertEqual(
                    self.picker("acalderon32@ucmerced.edu", app_label, model_name), ([str(self.ana.pk)], False)
                )

    def test_handle_returns_the_exact_handle_first_in_every_picker(self):
        for app_label, model_name in MEMBER_PICKERS:
            with self.subTest(picker=model_name):
                self.assertEqual(
                    self.picker("blewis28", app_label, model_name), ([str(self.brian.pk), str(self.bea.pk)], False)
                )

    def test_exact_handle_is_on_the_first_page_among_many_newer_partial_matches(self):
        for index in range(25):
            _member(
                "Bulk", "Lewis", f"blewis28.{index}@gmail.com", joined=_joined(2025, 1) + datetime.timedelta(days=index)
            )
        ids, more = self.picker("blewis28")
        self.assertEqual(len(ids), 20)
        self.assertTrue(more)
        self.assertEqual(ids[0], str(self.brian.pk))

    def test_phone_number_finds_the_member_in_a_picker(self):
        for term in ("(209) 765-4100", "+1 209 765 4100", "2097654100"):
            with self.subTest(term=term):
                ids, _more = self.picker(term, "event", "eventregistration")
                self.assertEqual(ids[0], str(self.ana.pk))

    def test_full_name_in_a_picker(self):
        self.assertEqual(self.picker("Brian Lewis", "authn", "contactphone"), ([str(self.brian.pk)], False))

    def test_empty_term_keeps_the_usual_newest_first_page(self):
        ids, more = self.picker("")
        self.assertTrue(more)
        expected = Member.objects.order_by("-date_joined").values_list("pk", flat=True)[:20]
        self.assertEqual(ids, [str(pk) for pk in expected])


class MemberAdminSearchResultsUnitTests(TestCase):
    """``MemberAdmin.get_search_results`` called directly, as the changelist and the autocomplete do."""

    @classmethod
    def setUpTestData(cls):
        cls.ana = _member("Ana", "Calderon", "acalderon32@ucmerced.edu", joined=_joined(2020, 1), phone="2097654100")
        cls.other = _member("Omar", "Other", "omar@example.org", joined=_joined(2021, 1), phone="2093228000")

    def setUp(self):
        cache.clear()
        self.admin = MemberAdmin(Member, site)
        self.factory = RequestFactory()

    def _results(self, term, **params):
        request = self.factory.get(CHANGELIST, {"q": term, **params})
        return self.admin.get_search_results(request, Member.objects.order_by("-date_joined"), term)

    def _stock(self, term):
        """Django's own search over the same ``search_fields``, without the phone digits or the rank."""
        request = self.factory.get(CHANGELIST, {"q": term})
        queryset, _dups = ModelAdmin.get_search_results(self.admin, request, Member.objects.all(), term)
        return set(queryset.distinct())

    def test_terms_with_too_few_digits_add_no_phone_matches(self):
        for term in ("32", "28", "+1", "(2) 8", "Ana 209", "acalderon32@ucmerced.edu", "blewis28"):
            with self.subTest(term=term):
                queryset, _dups = self._results(term)
                self.assertEqual(set(queryset.distinct()), self._stock(term))

    def test_phone_term_adds_phone_matches_and_reports_duplicates(self):
        queryset, may_have_duplicates = self._results("322-8000")
        self.assertTrue(may_have_duplicates)
        self.assertIn(self.other, set(queryset.distinct()))

    def _ranks(self, queryset):
        return [(member, member.rank) for member in queryset.annotate(rank=F("search_rank")).distinct()]

    def test_rank_orders_exact_first_without_selecting_it(self):
        queryset, _dups = self._results("acalderon32@ucmerced.edu")
        self.assertEqual(self._ranks(queryset), [(self.ana, 0)])
        self.assertEqual(queryset.query.order_by[0], "search_rank")
        self.assertNotIn("search_rank", queryset.query.annotation_select)
        self.assertEqual(queryset.distinct().count(), 1)

    def test_exact_phone_ranks_close(self):
        queryset, _dups = self._results("(209) 765-4100")
        self.assertEqual(self._ranks(queryset), [(self.ana, 1)])

    def test_handle_ranks_close_and_the_rest_last(self):
        bianca = _member("Bianca", "Lewis", "blewis281@gmail.com", joined=_joined(2022, 1))
        brian = _member("Brian", "Lewis", "blewis28@ucmerced.edu", joined=_joined(2019, 1))
        queryset, _dups = self._results("blewis28")
        self.assertEqual(self._ranks(queryset), [(brian, 1), (bianca, 2)])

    def test_no_rank_without_a_term_or_with_a_column_sort(self):
        for term, params in (("", {}), ("   ", {}), ("Ana Calderon", {}), ("acalderon32@ucmerced.edu", {"o": "2"})):
            with self.subTest(term=term, params=params):
                queryset, _dups = self._results(term, **params)
                self.assertNotIn("search_rank", queryset.query.annotations)
                self.assertEqual(queryset.query.order_by, ("-date_joined",))

    def test_rank_keeps_the_model_ordering_when_the_queryset_has_none(self):
        request = self.factory.get(CHANGELIST)
        queryset, _dups = self.admin.get_search_results(request, Member.objects.all(), "blewis28")
        self.assertEqual(queryset.query.order_by, ("search_rank", *Member._meta.ordering))

    def test_rank_adds_no_ordering_to_a_queryset_that_cleared_it(self):
        request = self.factory.get(CHANGELIST)
        queryset, _dups = self.admin.get_search_results(request, Member.objects.order_by(), "blewis28")
        self.assertEqual(queryset.query.order_by, ("search_rank",))
