import datetime

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from cms.models import CMSPage, NewsArticle, PageView
from core.services.db_tools.tool_modules.analytics import get_page_views
from core.services.db_tools.tool_modules.cms import search_cms_pages, search_news
from core.services.db_tools.tool_modules.custom.query import is_allowed_query_key, run_custom_query
from projects.models import Semester


class SearchCmsPagesToolTests(TestCase):
    def setUp(self):
        self.p1 = CMSPage.objects.create(title="About Us", slug="about", route="/about", status="published")
        self.p2 = CMSPage.objects.create(title="Contact", slug="contact", route="/contact", status="draft")

    def test_returns_all_with_no_filters(self):
        result = search_cms_pages({})
        self.assertIn("About Us", result)
        self.assertIn("Contact", result)

    def test_filters_by_title(self):
        result = search_cms_pages({"title": "About"})
        self.assertIn("About Us", result)
        self.assertNotIn("Contact", result)

    def test_filters_by_status(self):
        result = search_cms_pages({"status": "draft"})
        self.assertIn("Contact", result)
        self.assertNotIn("About Us", result)


class SearchNewsToolTests(TestCase):
    def setUp(self):
        self.a1 = NewsArticle.objects.create(
            title="Research Award",
            source="ucmerced",
            source_guid="guid-1",
            source_url="https://example.com/1",
            author="Jane",
            published_at=timezone.now(),
        )
        self.a2 = NewsArticle.objects.create(
            title="New Building",
            source="external",
            source_guid="guid-2",
            source_url="https://example.com/2",
            author="John",
            published_at=timezone.now() - datetime.timedelta(days=5),
        )

    def test_returns_all_with_no_filters(self):
        result = search_news({})
        self.assertIn("Research Award", result)
        self.assertIn("New Building", result)

    def test_filters_by_title(self):
        result = search_news({"title": "Research"})
        self.assertIn("Research Award", result)
        self.assertNotIn("New Building", result)

    def test_filters_by_source(self):
        result = search_news({"source": "external"})
        self.assertIn("New Building", result)
        self.assertNotIn("Research Award", result)


class GetPageViewsToolTests(TestCase):
    def setUp(self):
        PageView.objects.create(path="/about")
        PageView.objects.create(path="/about")
        PageView.objects.create(path="/contact")

    def test_returns_total_views(self):
        result = get_page_views({})
        self.assertIn("Total views: 3", result)

    def test_filters_by_path(self):
        result = get_page_views({"path": "/about", "count_only": True})
        self.assertEqual(result, "Page view count: 2")

    def test_count_only_mode(self):
        result = get_page_views({"count_only": True})
        self.assertEqual(result, "Page view count: 3")


class RunCustomQueryToolTests(TestCase):
    def setUp(self):
        self.sem = Semester.objects.create(year=2025, season=1, is_published=True)

    def test_queries_allowed_model(self):
        result = run_custom_query({"model": "Semester"})
        self.assertIn("2025", result)

    def test_unknown_model_returns_error(self):
        result = run_custom_query({"model": "FakeModel"})
        self.assertIn("Unknown model", result)

    def test_filters_with_allowed_field(self):
        Semester.objects.create(year=2024, season=2, is_published=False)
        result = run_custom_query({"model": "Semester", "filters": {"is_published": True}})
        self.assertIn("2025", result)
        self.assertNotIn("2024", result)

    def test_rejects_disallowed_filter_field(self):
        result = run_custom_query({"model": "Semester", "filters": {"is_deleted": True}})
        self.assertIn("Filter error", result)

    def test_ordering_by_allowed_field(self):
        Semester.objects.create(year=2024, season=2)
        result = run_custom_query({"model": "Semester", "ordering": "-year"})
        self.assertIn("2025", result)

    def test_rejects_disallowed_ordering_field(self):
        result = run_custom_query({"model": "Semester", "ordering": "-is_deleted"})
        self.assertIn("Ordering error", result)

    def test_count_only(self):
        result = run_custom_query({"model": "Semester", "count_only": True})
        self.assertEqual(result, "Count: 1")

    def test_custom_fields_output(self):
        result = run_custom_query({"model": "Semester", "fields": ["year", "season"]})
        self.assertIn("2025", result)

    def test_rejects_invalid_output_fields(self):
        result = run_custom_query({"model": "Semester", "fields": ["password"]})
        self.assertIn("Fields error", result)

    def test_limit_caps_at_max_rows(self):
        result = run_custom_query({"model": "Semester", "limit": 9999})
        self.assertIn("2025", result)


class IsAllowedQueryKeyTests(SimpleTestCase):
    def test_allowed_field_no_lookup(self):
        self.assertTrue(is_allowed_query_key("Member", "first_name"))

    def test_allowed_field_with_safe_lookup(self):
        self.assertTrue(is_allowed_query_key("Member", "first_name__icontains"))

    def test_disallowed_field(self):
        self.assertFalse(is_allowed_query_key("Member", "password"))

    def test_unsafe_lookup_rejected(self):
        self.assertFalse(is_allowed_query_key("Member", "first_name__regex"))

    def test_triple_underscore_rejected(self):
        self.assertFalse(is_allowed_query_key("Member", "first_name__foo__bar"))

    def test_unknown_model_rejects_all(self):
        self.assertFalse(is_allowed_query_key("FakeModel", "anything"))
