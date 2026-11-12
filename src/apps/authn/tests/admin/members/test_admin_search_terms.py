"""How the member and contact admin searches read a term: which terms are phone numbers, and the email ranking."""

from django.contrib.admin import ModelAdmin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.authn.admin.members.search import (
    MIN_PHONE_DIGITS,
    RankedSearchMixin,
    contact_email_search_rank,
    contact_phone_search_rank,
    email_terms,
    member_search_rank,
    phone_digits,
    search_text,
)
from apps.authn.models import ContactEmail


class PhoneDigitsTests(SimpleTestCase):
    def test_phone_shaped_terms_give_national_digits(self):
        cases = {
            "2097654100": "2097654100",
            "(209) 765-4100": "2097654100",
            "209.765.4100": "2097654100",
            " 209 765 4100 ": "2097654100",
            "+1 209 765 4100": "2097654100",
            "+1 (209) 765-4100": "2097654100",
            "+12097654100": "2097654100",
            "12097654100": "2097654100",
            "1-209-765-4100": "2097654100",
            "+1 209": "209",
            "765-4100": "7654100",
            "555": "555",
            "1555": "1555",
            "+44 20 7946 0958": "442079460958",
            '"555 123"': "555123",
        }
        for term, expected in cases.items():
            with self.subTest(term=term):
                self.assertEqual(phone_digits(term), expected)

    def test_other_terms_are_not_phone_numbers(self):
        for term in (
            "",
            None,
            "   ",
            "acalderon32@ucmerced.edu",
            "blewis28",
            "Ana 209",
            "209 Ana",
            "32",
            "28",
            "+1",
            "+1 20",
            "(2) 8",
            "---",
            "２０９７６５４１００",  # full-width digits are not what a stored number holds
            "209-765-4100 x12",
            "tel:2097654100",
        ):
            with self.subTest(term=term):
                self.assertEqual(phone_digits(term), "")

    def test_minimum_is_three_digits(self):
        self.assertEqual(MIN_PHONE_DIGITS, 3)
        self.assertEqual(phone_digits("209"), "209")
        self.assertEqual(phone_digits("20"), "")


class SearchTextTests(SimpleTestCase):
    def test_strips_spaces_and_one_pair_of_matching_quotes(self):
        self.assertEqual(search_text('  "blewis28"  '), "blewis28")
        self.assertEqual(search_text("'blewis28'"), "blewis28")
        self.assertEqual(search_text("\"blewis28'"), "\"blewis28'")
        self.assertEqual(search_text('"'), '"')
        self.assertEqual(search_text(None), "")


class EmailTermsTests(SimpleTestCase):
    def test_address_and_handle(self):
        self.assertEqual(
            email_terms("acalderon32@ucmerced.edu"), ("acalderon32@ucmerced.edu", "acalderon32@ucmerced.edu")
        )
        self.assertEqual(email_terms("blewis28"), ("", "blewis28@"))
        self.assertEqual(email_terms("blewis28@"), ("blewis28@", "blewis28@"))
        self.assertEqual(email_terms(' "blewis28" '), ("", "blewis28@"))

    def test_terms_that_cannot_be_one_address(self):
        for term in ("", "   ", "@ucmerced.edu", "Ana Calderon", "blewis 28"):
            with self.subTest(term=term):
                self.assertEqual(email_terms(term), ("", ""))


class RankExpressionTests(SimpleTestCase):
    def test_no_rank_when_nothing_can_rank_first(self):
        self.assertIsNone(member_search_rank("Ana Calderon"))
        self.assertIsNone(contact_email_search_rank("Ana Calderon"))
        self.assertIsNone(contact_phone_search_rank("blewis28"))
        self.assertIsNone(member_search_rank(""))

    def test_member_rank_tiers(self):
        self.assertEqual(len(member_search_rank("acalderon32@ucmerced.edu").cases), 2)
        self.assertEqual(len(member_search_rank("blewis28").cases), 1)
        self.assertEqual(len(member_search_rank("(209) 765-4100").cases), 1)
        self.assertEqual(len(member_search_rank("2097654100").cases), 2)


class MixinDefaultsTests(TestCase):
    def test_without_a_phone_field_or_rank_the_mixin_is_the_stock_search(self):
        class PlainAdmin(RankedSearchMixin, ModelAdmin):
            search_fields = ("email_address",)

        admin = PlainAdmin(ContactEmail, AdminSite())
        request = RequestFactory().get("/admin/authn/contactemail/", {"q": "2097654100"})
        for term in ("2097654100", "blewis28", "jdoe@example.edu"):
            with self.subTest(term=term):
                queryset, dups = admin.get_search_results(request, ContactEmail.objects.all(), term)
                stock, stock_dups = ModelAdmin.get_search_results(admin, request, ContactEmail.objects.all(), term)
                self.assertEqual(str(queryset.query), str(stock.query))
                self.assertEqual(dups, stock_dups)
