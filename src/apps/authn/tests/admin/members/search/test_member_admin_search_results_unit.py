from django.contrib.admin import ModelAdmin
from django.contrib.admin.sites import site
from django.core.cache import cache
from django.db.models import F
from django.test import RequestFactory, TestCase

from apps.authn.admin.members.member import MemberAdmin
from apps.authn.tests.admin.members.search.test_member_admin_exact_search import CHANGELIST, Member, _joined, _member


class MemberAdminSearchResultsUnitTests(TestCase):
    """``MemberAdmin.get_search_results`` called directly, as the changelist and the autocomplete do."""

    @classmethod
    def setUpTestData(cls):
        cls.ana = _member("Ana", "Quill", "aquill32@example.edu", joined=_joined(2020, 1), phone="2097654100")
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
        for term in ("32", "28", "+1", "(2) 8", "Ana 209", "aquill32@example.edu", "bfenwick28"):
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
        queryset, _dups = self._results("aquill32@example.edu")
        self.assertEqual(self._ranks(queryset), [(self.ana, 0)])
        self.assertEqual(queryset.query.order_by[0], "search_rank")
        self.assertNotIn("search_rank", queryset.query.annotation_select)
        self.assertEqual(queryset.distinct().count(), 1)

    def test_exact_phone_ranks_close(self):
        queryset, _dups = self._results("(209) 765-4100")
        self.assertEqual(self._ranks(queryset), [(self.ana, 1)])

    def test_handle_ranks_close_and_the_rest_last(self):
        bianca = _member("Bianca", "Fenwick", "bfenwick281@example.net", joined=_joined(2022, 1))
        brian = _member("Brian", "Fenwick", "bfenwick28@example.edu", joined=_joined(2019, 1))
        queryset, _dups = self._results("bfenwick28")
        self.assertEqual(self._ranks(queryset), [(brian, 1), (bianca, 2)])

    def test_no_rank_without_a_term_or_with_a_column_sort(self):
        for term, params in (("", {}), ("   ", {}), ("Ana Quill", {}), ("aquill32@example.edu", {"o": "2"})):
            with self.subTest(term=term, params=params):
                queryset, _dups = self._results(term, **params)
                self.assertNotIn("search_rank", queryset.query.annotations)
                self.assertEqual(queryset.query.order_by, ("-date_joined",))

    def test_rank_keeps_the_model_ordering_when_the_queryset_has_none(self):
        request = self.factory.get(CHANGELIST)
        queryset, _dups = self.admin.get_search_results(request, Member.objects.all(), "bfenwick28")
        self.assertEqual(queryset.query.order_by, ("search_rank", *Member._meta.ordering))

    def test_rank_adds_no_ordering_to_a_queryset_that_cleared_it(self):
        request = self.factory.get(CHANGELIST)
        queryset, _dups = self.admin.get_search_results(request, Member.objects.order_by(), "bfenwick28")
        self.assertEqual(queryset.query.order_by, ("search_rank",))
