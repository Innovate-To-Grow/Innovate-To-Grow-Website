"""Tests for the System Intelligence database query tools."""

import json

from django.test import TestCase
from django.utils import timezone

from apps.event.tests.helpers import make_admin
from apps.system_intelligence.services.query_tools import execute_tool, get_tool_definitions
from apps.system_intelligence.services.query_tools.tool_modules.domains.analytics import get_page_views
from apps.system_intelligence.services.query_tools.tool_modules.domains.cms import search_cms_pages, search_news
from apps.system_intelligence.services.query_tools.tool_modules.domains.helpers import _serialize_rows, _truncate

# ---------- helpers ----------


class HelpersTest(TestCase):
    def test_truncate_short_text_unchanged(self):
        self.assertEqual(_truncate("hello", limit=100), "hello")

    def test_truncate_long_text(self):
        text = "x" * 50
        result = _truncate(text, limit=10)
        self.assertTrue(result.startswith("x" * 10))
        self.assertIn("truncated, 50 total chars", result)

    def test_serialize_rows_serializes_datetime_and_uuid(self):
        from apps.projects.models import Semester

        Semester.objects.create(year=2025, season=1, is_published=True)
        result = _serialize_rows(Semester.objects.all(), ["id", "year", "created_at"])
        self.assertIn("Showing 1 of 1 result(s).", result)
        payload = json.loads(result.split("\n", 1)[1])
        # id is a UUID -> serialized as string; created_at is a datetime -> isoformat string.
        self.assertIsInstance(payload[0]["id"], str)
        self.assertIsInstance(payload[0]["created_at"], str)


# ---------- executor ----------


class ExecuteToolTest(TestCase):
    def test_unknown_tool(self):
        self.assertEqual(execute_tool({"name": "nope"}), "Unknown tool: nope")

    def test_known_tool_runs(self):
        from apps.projects.models import Semester

        Semester.objects.create(year=2025, season=1, is_published=True)
        user = make_admin()
        result = execute_tool({"name": "search_semesters", "input": {"year": 2025}}, user=user)
        self.assertIn("2025", result)

    def test_tool_error_is_caught(self):
        from unittest.mock import patch

        def boom(_params):
            raise ValueError("kaboom")

        with patch.dict(
            "apps.system_intelligence.services.query_tools.tool_modules.dispatch.executor.TOOL_REGISTRY",
            {"search_projects": boom},
        ):
            user = make_admin()
            result = execute_tool({"name": "search_projects", "input": {}}, user=user)
        self.assertIn("Tool error: kaboom", result)


# ---------- definitions ----------


class DefinitionsTest(TestCase):
    def test_returns_list_of_tool_defs(self):
        defs = get_tool_definitions()
        self.assertIsInstance(defs, list)
        self.assertGreater(len(defs), 0)

    def test_search_events_contract_uses_registration_and_date_range(self):
        definition = next(item for item in get_tool_definitions() if item["toolSpec"]["name"] == "search_events")
        properties = definition["toolSpec"]["inputSchema"]["json"]["properties"]

        self.assertNotIn("is_live", properties)
        self.assertIn("registration_open", properties)
        self.assertIn("date_from", properties)
        self.assertIn("date_to", properties)


# ---------- analytics ----------


class AnalyticsTest(TestCase):
    def _make_view(self, path="/home/"):
        from apps.cms.models import PageView

        return PageView.objects.create(path=path, timestamp=timezone.now())

    def test_count_only(self):
        self._make_view()
        self._make_view("/about/")
        result = get_page_views({"count_only": True})
        self.assertEqual(result, "Page view count: 2")

    def test_filters_and_summary(self):
        self._make_view("/blog/")
        result = get_page_views(
            {
                "path": "blog",
                "date_from": "2000-01-01T00:00:00+00:00",
                "date_to": "2999-01-01T00:00:00+00:00",
            }
        )
        self.assertIn("Total views: 1", result)
        self.assertIn("Top pages:", result)


# ---------- cms ----------


class CmsToolsTest(TestCase):
    def test_search_cms_pages_filters(self):
        from apps.cms.models import CMSPage

        CMSPage.objects.create(title="About Us", slug="about", route="/about", status="published")
        result = search_cms_pages({"title": "About", "slug": "about", "status": "published"})
        self.assertIn("About Us", result)

    def test_search_news_filters(self):
        from apps.cms.models import NewsArticle

        NewsArticle.objects.create(
            source="rss",
            source_guid="g1",
            title="Big News",
            source_url="https://x.com",
            published_at=timezone.now(),
        )
        result = search_news(
            {
                "title": "Big",
                "source": "rss",
                "date_from": "2000-01-01T00:00:00+00:00",
                "date_to": "2999-01-01T00:00:00+00:00",
            }
        )
        self.assertIn("Big News", result)


# ---------- events ----------


# ---------- mail ----------


# ---------- members ----------


# ---------- projects ----------


# ---------- custom query ----------
