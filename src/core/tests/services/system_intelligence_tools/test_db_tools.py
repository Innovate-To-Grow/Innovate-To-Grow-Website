import datetime
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from cms.models import CMSPage, NewsArticle, PageView
from core.services.db_tools.executor import execute_tool
from core.services.db_tools.tool_modules.analytics import get_page_views
from core.services.db_tools.tool_modules.cms import search_cms_pages, search_news
from core.services.db_tools.tool_modules.custom.query import is_allowed_query_key, run_custom_query
from core.services.db_tools.tool_modules.events import get_checkin_stats, get_event_registrations, search_events
from core.services.db_tools.tool_modules.mail import get_campaign_stats, search_email_campaigns
from core.services.db_tools.tool_modules.members import count_members, search_members
from core.services.db_tools.tool_modules.projects import search_projects, search_semesters
from event.models import CheckIn, CheckInRecord
from event.tests.helpers import make_event, make_member, make_registration, make_ticket
from mail.models import EmailCampaign, RecipientLog
from projects.models import Project, Semester


class ExecuteToolDispatchTests(TestCase):
    def test_dispatches_to_registered_tool(self):
        result = execute_tool({"name": "count_members", "toolUseId": "t1", "input": {}})
        self.assertIn("Count:", result)

    def test_unknown_tool_returns_error_message(self):
        result = execute_tool({"name": "nonexistent_tool", "toolUseId": "t1", "input": {}})
        self.assertEqual(result, "Unknown tool: nonexistent_tool")

    def test_empty_name_returns_unknown(self):
        result = execute_tool({"name": "", "toolUseId": "t1", "input": {}})
        self.assertEqual(result, "Unknown tool: ")

    def test_missing_name_returns_unknown(self):
        result = execute_tool({"toolUseId": "t1", "input": {}})
        self.assertEqual(result, "Unknown tool: ")

    @patch("core.services.db_tools.executor.TOOL_REGISTRY", {"boom": lambda p: 1 / 0})
    def test_exception_returns_tool_error(self):
        result = execute_tool({"name": "boom", "toolUseId": "t1", "input": {}})
        self.assertIn("Tool error:", result)


class SearchMembersToolTests(TestCase):
    def setUp(self):
        self.alice = make_member(email="alice@corp.com", first_name="Alice", last_name="Smith")
        self.alice.organization = "WidgetCo"
        self.alice.is_staff = True
        self.alice.save()
        self.bob = make_member(email="bob@corp.com", first_name="Bob", last_name="Jones")
        self.bob.organization = "Gadgets Inc"
        self.bob.save()

    def test_returns_all_with_no_filters(self):
        result = search_members({})
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)

    def test_filters_by_name(self):
        result = search_members({"name": "Alice"})
        self.assertIn("Alice", result)
        self.assertNotIn("Bob", result)

    def test_filters_by_email(self):
        result = search_members({"email": "bob@corp"})
        self.assertIn("Bob", result)
        self.assertNotIn("Alice", result)

    def test_filters_by_organization(self):
        result = search_members({"organization": "Widget"})
        self.assertIn("Alice", result)
        self.assertNotIn("Bob", result)

    def test_filters_by_is_staff(self):
        result = search_members({"is_staff": True})
        self.assertIn("Alice", result)
        self.assertNotIn("Bob", result)

    def test_filters_by_is_active_false(self):
        self.bob.is_active = False
        self.bob.save()
        result = search_members({"is_active": False})
        self.assertIn("Bob", result)
        self.assertNotIn("Alice", result)


class CountMembersToolTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="c1@test.com", first_name="C1", last_name="M")
        self.m1.is_staff = True
        self.m1.save()
        self.m2 = make_member(email="c2@test.com", first_name="C2", last_name="M")
        self.m3 = make_member(email="c3@test.com", first_name="C3", last_name="M")
        self.m3.is_active = False
        self.m3.save()

    def test_counts_all(self):
        result = count_members({})
        self.assertIn("Count:", result)
        self.assertIn("3", result)

    def test_counts_staff_only(self):
        result = count_members({"is_staff": True})
        self.assertEqual(result, "Count: 1")

    def test_counts_active_only(self):
        result = count_members({"is_active": True})
        self.assertEqual(result, "Count: 2")


class SearchEventsToolTests(TestCase):
    def setUp(self):
        self.e1 = make_event(name="Spring Showcase", date=datetime.date(2025, 4, 10))
        self.e2 = make_event(name="Fall Expo", date=datetime.date(2025, 10, 20), is_live=True)

    def test_returns_all_with_no_filters(self):
        result = search_events({})
        self.assertIn("Spring Showcase", result)
        self.assertIn("Fall Expo", result)

    def test_filters_by_name(self):
        result = search_events({"name": "Spring"})
        self.assertIn("Spring Showcase", result)
        self.assertNotIn("Fall Expo", result)

    def test_filters_by_is_live(self):
        result = search_events({"is_live": True})
        self.assertIn("Fall Expo", result)
        self.assertNotIn("Spring Showcase", result)

    def test_filters_by_date_range(self):
        result = search_events({"date_from": "2025-06-01"})
        self.assertIn("Fall Expo", result)
        self.assertNotIn("Spring Showcase", result)


class GetEventRegistrationsToolTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="r1@test.com", first_name="Reg", last_name="One")
        self.event = make_event(name="Demo Day")
        self.ticket = make_ticket(self.event)
        make_registration(self.m1, self.event, self.ticket, attendee_email="r1@test.com", attendee_first_name="Reg")

    def test_returns_registrations_for_event_name(self):
        result = get_event_registrations({"event_name": "Demo"})
        self.assertIn("Reg", result)

    def test_returns_registrations_for_event_id(self):
        result = get_event_registrations({"event_id": str(self.event.pk)})
        self.assertIn("Reg", result)

    def test_count_only_returns_count(self):
        result = get_event_registrations({"event_name": "Demo", "count_only": True})
        self.assertEqual(result, "Registration count: 1")


class GetCheckinStatsToolTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="ci1@test.com", first_name="Ci", last_name="One")
        self.event = make_event(name="Hackathon")
        self.ticket = make_ticket(self.event)
        self.reg = make_registration(self.m1, self.event, self.ticket)
        self.checkin = CheckIn.objects.create(event=self.event, name="Front Desk")
        CheckInRecord.objects.create(check_in=self.checkin, registration=self.reg)

    def test_returns_total_checkins(self):
        result = get_checkin_stats({"event_name": "Hackathon"})
        self.assertIn("Total check-ins: 1", result)

    def test_groups_by_station(self):
        result = get_checkin_stats({"event_name": "Hackathon"})
        self.assertIn("Front Desk", result)

    def test_empty_for_unknown_event(self):
        result = get_checkin_stats({"event_name": "Nonexistent"})
        self.assertIn("Total check-ins: 0", result)


class SearchProjectsToolTests(TestCase):
    def setUp(self):
        self.sem = Semester.objects.create(year=2025, season=1)
        self.p1 = Project.objects.create(
            semester=self.sem,
            project_title="Smart Farm",
            team_name="Alpha",
            team_number="CAP-101",
            organization="AgroCo",
            industry="Agriculture",
            class_code="CAP",
        )
        self.p2 = Project.objects.create(
            semester=self.sem,
            project_title="Campus Nav",
            team_name="Beta",
            team_number="CSE-201",
            organization="UC Merced",
            industry="Education",
            class_code="CSE",
        )

    def test_returns_all_with_no_filters(self):
        result = search_projects({})
        self.assertIn("Smart Farm", result)
        self.assertIn("Campus Nav", result)

    def test_filters_by_title(self):
        result = search_projects({"title": "Smart"})
        self.assertIn("Smart Farm", result)
        self.assertNotIn("Campus Nav", result)

    def test_filters_by_organization(self):
        result = search_projects({"organization": "UC Merced"})
        self.assertIn("Campus Nav", result)
        self.assertNotIn("Smart Farm", result)

    def test_filters_by_class_code(self):
        result = search_projects({"class_code": "CAP"})
        self.assertIn("Smart Farm", result)
        self.assertNotIn("Campus Nav", result)

    def test_filters_by_semester(self):
        result = search_projects({"semester": "Spring"})
        self.assertIn("Smart Farm", result)


class SearchSemestersToolTests(TestCase):
    def setUp(self):
        self.s1 = Semester.objects.create(year=2025, season=1, is_published=True)
        self.s2 = Semester.objects.create(year=2024, season=2, is_published=False)

    def test_returns_all(self):
        result = search_semesters({})
        self.assertIn("2025", result)
        self.assertIn("2024", result)

    def test_filters_by_year(self):
        result = search_semesters({"year": 2025})
        self.assertIn("2025", result)
        self.assertNotIn("2024", result)

    def test_filters_by_is_published(self):
        result = search_semesters({"is_published": True})
        self.assertIn("2025", result)
        self.assertNotIn("2024", result)


class SearchEmailCampaignsToolTests(TestCase):
    def setUp(self):
        self.c1 = EmailCampaign.objects.create(subject="Welcome new members", status="sent")
        self.c2 = EmailCampaign.objects.create(subject="Event reminder", status="draft")

    def test_returns_all_with_no_filters(self):
        result = search_email_campaigns({})
        self.assertIn("Welcome", result)
        self.assertIn("Event reminder", result)

    def test_filters_by_name(self):
        result = search_email_campaigns({"name": "Welcome"})
        self.assertIn("Welcome", result)
        self.assertNotIn("Event reminder", result)

    def test_filters_by_status(self):
        result = search_email_campaigns({"status": "draft"})
        self.assertIn("Event reminder", result)
        self.assertNotIn("Welcome", result)


class GetCampaignStatsToolTests(TestCase):
    def setUp(self):
        self.campaign = EmailCampaign.objects.create(
            subject="Stats test", status="sent", total_recipients=3, sent_count=2, failed_count=1
        )
        RecipientLog.objects.create(campaign=self.campaign, email_address="a@b.com", status="sent")
        RecipientLog.objects.create(campaign=self.campaign, email_address="c@d.com", status="sent")
        RecipientLog.objects.create(campaign=self.campaign, email_address="e@f.com", status="failed")

    def test_returns_stats_for_campaign_by_name(self):
        result = get_campaign_stats({"campaign_name": "Stats test"})
        self.assertIn("Stats test", result)
        self.assertIn("Sent: 2", result)
        self.assertIn("Failed: 1", result)

    def test_returns_stats_for_campaign_by_id(self):
        result = get_campaign_stats({"campaign_id": str(self.campaign.pk)})
        self.assertIn("Stats test", result)

    def test_not_found_for_unknown_campaign(self):
        result = get_campaign_stats({"campaign_name": "nonexistent"})
        self.assertEqual(result, "No campaign found matching the criteria.")

    def test_delivery_breakdown_included(self):
        result = get_campaign_stats({"campaign_name": "Stats test"})
        self.assertIn("Delivery breakdown:", result)


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
