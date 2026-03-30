"""Tests for CMS route normalization and validation edge cases."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from cms.models import CMSPage
from cms.models.content.cms.cms_page import normalize_cms_route, validate_cms_route


class NormalizeCmsRouteTests(TestCase):
    def test_empty_string(self):
        self.assertEqual(normalize_cms_route(""), "/")

    def test_none(self):
        self.assertEqual(normalize_cms_route(None), "/")

    def test_whitespace_only(self):
        self.assertEqual(normalize_cms_route("   "), "/")

    def test_single_slash(self):
        self.assertEqual(normalize_cms_route("/"), "/")

    def test_multiple_slashes(self):
        self.assertEqual(normalize_cms_route("///"), "/")

    def test_trailing_slash_stripped(self):
        self.assertEqual(normalize_cms_route("/about/"), "/about")

    def test_leading_slash_added(self):
        self.assertEqual(normalize_cms_route("about"), "/about")

    def test_consecutive_slashes_collapsed(self):
        self.assertEqual(normalize_cms_route("//about///page//"), "/about/page")

    def test_whitespace_around_segments(self):
        self.assertEqual(normalize_cms_route("/ about / page /"), "/about/page")

    def test_deeply_nested_route(self):
        self.assertEqual(normalize_cms_route("/a/b/c/d/e"), "/a/b/c/d/e")

    def test_single_segment_no_leading_slash(self):
        self.assertEqual(normalize_cms_route("home"), "/home")


class ValidateCmsRouteTests(TestCase):
    def test_root_route_valid(self):
        self.assertEqual(validate_cms_route("/"), "/")

    def test_simple_route_valid(self):
        self.assertEqual(validate_cms_route("/about"), "/about")

    def test_hyphenated_segment_valid(self):
        self.assertEqual(validate_cms_route("/about-us"), "/about-us")

    def test_underscored_segment_valid(self):
        self.assertEqual(validate_cms_route("/about_us"), "/about_us")

    def test_mixed_case_valid(self):
        self.assertEqual(validate_cms_route("/About-Us"), "/About-Us")

    def test_numeric_segment_valid(self):
        self.assertEqual(validate_cms_route("/page1"), "/page1")

    def test_segment_with_spaces_invalid(self):
        with self.assertRaises(ValidationError):
            validate_cms_route("/bad route")

    def test_segment_with_special_chars_invalid(self):
        with self.assertRaises(ValidationError):
            validate_cms_route("/bad@route")

    def test_segment_with_dots_invalid(self):
        with self.assertRaises(ValidationError):
            validate_cms_route("/bad.route")

    def test_segment_starting_with_hyphen_invalid(self):
        with self.assertRaises(ValidationError):
            validate_cms_route("/-invalid")

    def test_segment_starting_with_underscore_invalid(self):
        with self.assertRaises(ValidationError):
            validate_cms_route("/_invalid")

    def test_segment_ending_with_hyphen_invalid(self):
        with self.assertRaises(ValidationError):
            validate_cms_route("/invalid-")

    def test_consecutive_hyphens_invalid(self):
        with self.assertRaises(ValidationError):
            validate_cms_route("/bad--route")

    def test_empty_normalizes_to_root(self):
        self.assertEqual(validate_cms_route(""), "/")


class CMSPageCleanTests(TestCase):
    def test_clean_normalizes_and_validates_route(self):
        page = CMSPage(slug="test", route="about//page/", title="Test")
        page.full_clean()
        self.assertEqual(page.route, "/about/page")

    def test_clean_invalid_route_raises_field_error(self):
        page = CMSPage(slug="test", route="/bad route!", title="Test")
        with self.assertRaises(ValidationError) as ctx:
            page.full_clean()
        self.assertIn("route", ctx.exception.message_dict)

    def test_published_at_preserved_on_re_save(self):
        page = CMSPage.objects.create(slug="pub", route="/pub", title="Published", status="published")
        original_published_at = page.published_at

        page.title = "Updated Title"
        page.save()
        page.refresh_from_db()
        self.assertEqual(page.published_at, original_published_at)

    def test_published_at_not_set_for_archived(self):
        page = CMSPage.objects.create(slug="arch", route="/arch", title="Archived", status="archived")
        self.assertIsNone(page.published_at)
