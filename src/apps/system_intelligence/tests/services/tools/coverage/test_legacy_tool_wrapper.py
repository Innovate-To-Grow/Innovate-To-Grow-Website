import asyncio
import datetime

from django.core.cache import cache
from django.test import TransactionTestCase
from django.utils import timezone

from apps.cms.models import (
    NewsArticle,
    PageView,
)
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_registration,
    make_ticket,
)
from apps.mail.models import EmailCampaign, RecipientLog
from apps.projects.models import Project, Semester
from apps.system_intelligence.services import tools as si_tools


class LegacyToolWrapperTests(TransactionTestCase):
    """Each legacy wrapper dispatches through the local TOOL_REGISTRY."""

    def setUp(self):
        cache.clear()
        self.member = make_member(email="leg@example.com", first_name="Leg", last_name="Acy")
        self.semester = Semester.objects.create(year=2026, season=Semester.Season.SPRING, is_published=True)
        self.project = Project.objects.create(
            semester=self.semester,
            class_code="CSE",
            team_number="CSE-1",
            team_name="Team",
            project_title="Legacy Project",
            organization="UC Merced",
            industry="Tech",
        )
        self.event = make_event(name="Legacy Event", date=datetime.date(2026, 5, 1))
        self.ticket = make_ticket(self.event, name="General")
        make_registration(self.member, self.event, self.ticket, attendee_email="leg@example.com")
        self.campaign = EmailCampaign.objects.create(
            name="Legacy Campaign", subject="Subj", body="Body", status="sent", sent_count=1
        )
        RecipientLog.objects.create(campaign=self.campaign, email_address="leg@example.com", status="sent")
        PageView.objects.create(path="/legacy", session_key="s-legacy")
        NewsArticle.objects.create(
            source="ucm",
            source_guid="legacy-news",
            title="Legacy News",
            source_url="https://example.com/legacy",
            published_at=timezone.now(),
        )
        from apps.cms.models import CMSPage

        CMSPage.objects.create(title="Legacy Page", slug="legacy", route="/legacy", status="published")

    def test_search_members_wrapper(self):
        # legacy.py line 14 + run path; assert the registry result is returned.
        result = asyncio.run(si_tools.search_members(name="Leg"))
        self.assertIn("result", result)
        self.assertIn("Leg", result["result"])

    def test_count_members_wrapper(self):
        # legacy.py line 19 — exactly one member is seeded in setUp, so the
        # wrapper must report that count, not just the "Count:" label.
        from apps.authn.models import Member

        self.assertEqual(Member.objects.count(), 1)
        result = asyncio.run(si_tools.count_members())
        self.assertEqual(result["result"], "Count: 1")

    def test_search_events_wrapper(self):
        # legacy.py line 26.
        result = asyncio.run(si_tools.search_events(name="Legacy"))
        self.assertIn("Legacy Event", result["result"])

    def test_get_event_registrations_wrapper(self):
        # legacy.py line 33.
        result = asyncio.run(si_tools.get_event_registrations(event_name="Legacy Event"))
        self.assertIn("leg@example.com", result["result"].lower())

    def test_search_projects_wrapper(self):
        # legacy.py line 45.
        result = asyncio.run(si_tools.search_projects(title="Legacy"))
        self.assertIn("Legacy Project", result["result"])

    def test_search_email_campaigns_wrapper(self):
        # legacy.py line 50.
        result = asyncio.run(si_tools.search_email_campaigns(name="Legacy"))
        self.assertIn("Legacy Campaign", result["result"])

    def test_get_campaign_stats_wrapper(self):
        # legacy.py line 55.
        result = asyncio.run(si_tools.get_campaign_stats(campaign_name="Legacy Campaign"))
        self.assertIn("Legacy Campaign", result["result"])

    def test_search_cms_pages_wrapper(self):
        # legacy.py line 60.
        result = asyncio.run(si_tools.search_cms_pages(title="Legacy"))
        self.assertIn("Legacy Page", result["result"])

    def test_search_news_wrapper(self):
        # legacy.py line 67.
        result = asyncio.run(si_tools.search_news(title="Legacy"))
        self.assertIn("Legacy News", result["result"])

    def test_get_page_views_wrapper(self):
        # legacy.py line 74.
        result = asyncio.run(si_tools.get_page_views(path="/legacy"))
        self.assertIn("Total views", result["result"])

    def test_get_checkin_stats_wrapper(self):
        # legacy.py line 79.
        result = asyncio.run(si_tools.get_checkin_stats(event_name="Legacy Event"))
        self.assertIn("check-ins", result["result"].lower())

    def test_search_semesters_wrapper(self):
        # legacy.py line 84.
        result = asyncio.run(si_tools.search_semesters(year=2026))
        self.assertIn("2026", result["result"])

    def test_run_custom_query_wrapper(self):
        # legacy.py line 96.
        result = asyncio.run(si_tools.run_custom_query(model="Semester"))
        self.assertIn("2026", result["result"])
