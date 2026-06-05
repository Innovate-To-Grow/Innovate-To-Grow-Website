"""Tests for the public grounding-context builder."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.cms.models import CMSPage, NewsArticle
from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.projects.models import Project, Semester
from apps.system_intelligence.services.public_assistant import context


class BuildContextTests(TestCase):
    def setUp(self):
        # build_public_context caches its result; clear so each test (which
        # sets up different DB rows) sees a fresh build, not a bled-over one.
        cache.clear()

    def test_empty_when_no_data(self):
        self.assertEqual(context.build_public_context(), "")

    def test_includes_all_sources(self):
        schedule = CurrentProjectSchedule.objects.create(name="Spring 2026", is_active=True)
        CurrentProject.objects.create(
            schedule=schedule,
            project_title="Smart Irrigation",
            team_name="AquaTeam",
            organization="GreenCo",
            industry="AgTech",
        )
        semester = Semester.objects.create(year=2025, season=Semester.Season.FALL, is_published=True)
        Project.objects.create(semester=semester, project_title="Solar Tracker", organization="SunCorp")
        NewsArticle.objects.create(
            source_guid="guid-1",
            title="I2G Demo Day Recap",
            source_url="https://example.com/news/1",
            published_at=timezone.now(),
        )
        CMSPage.objects.create(slug="about", route="/about", title="About", status="published")

        result = context.build_public_context()
        self.assertIn("CURRENT PROJECTS", result)
        self.assertIn("Smart Irrigation", result)
        self.assertIn("PAST PROJECTS", result)
        self.assertIn("Solar Tracker", result)
        self.assertIn("RECENT NEWS", result)
        self.assertIn("I2G Demo Day Recap", result)
        self.assertIn("PUBLISHED PAGES", result)
        self.assertIn("/about", result)

    def test_char_cap_truncates(self):
        # Title stays within CMSPage.title's max_length=300 (PostgreSQL enforces
        # it; SQLite does not) while still producing context well over the cap.
        CMSPage.objects.create(slug="a", route="/a", title="A" * 200, status="published")
        result = context.build_public_context(char_cap=50)
        self.assertLessEqual(len(result), 50)

    def test_unpublished_data_excluded(self):
        semester = Semester.objects.create(year=2024, season=Semester.Season.SPRING, is_published=False)
        Project.objects.create(semester=semester, project_title="Hidden Project")
        CMSPage.objects.create(slug="draft", route="/draft", title="Draft", status="draft")
        result = context.build_public_context()
        self.assertNotIn("Hidden Project", result)
        self.assertNotIn("/draft", result)

    def test_section_failure_is_isolated(self):
        CMSPage.objects.create(slug="about", route="/about", title="About", status="published")
        # Make the current-projects section's underlying query blow up; the
        # builder must swallow it and still render the remaining sections.
        with patch("apps.event.models.CurrentProjectSchedule.load", side_effect=RuntimeError("boom")):
            result = context.build_public_context()
        # The failing section is skipped; the rest still renders.
        self.assertIn("/about", result)

    def test_schedule_without_projects_yields_no_current_section(self):
        CurrentProjectSchedule.objects.create(name="Empty", is_active=True)
        result = context.build_public_context()
        self.assertNotIn("CURRENT PROJECTS", result)

    def test_result_is_cached_between_calls(self):
        CMSPage.objects.create(slug="about", route="/about", title="About", status="published")
        first = context.build_public_context()
        self.assertIn("/about", first)
        # A new published page after the first (cached) build is NOT reflected
        # until the cache expires; use_cache=False forces a fresh build.
        CMSPage.objects.create(slug="contact", route="/contact", title="Contact", status="published")
        self.assertNotIn("/contact", context.build_public_context())
        self.assertIn("/contact", context.build_public_context(use_cache=False))

    def test_news_without_published_date_label(self):
        article = NewsArticle.objects.create(
            source_guid="guid-2",
            title="Dated Article",
            source_url="https://example.com/news/2",
            published_at=timezone.now() - timedelta(days=3),
        )
        result = context.build_public_context()
        self.assertIn(article.published_at.date().isoformat(), result)
