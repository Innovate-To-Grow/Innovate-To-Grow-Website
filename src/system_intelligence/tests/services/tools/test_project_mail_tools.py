from django.test import TestCase

from core.services.db_tools.tool_modules.mail import get_campaign_stats, search_email_campaigns
from core.services.db_tools.tool_modules.projects import search_projects, search_semesters
from mail.models import EmailCampaign, RecipientLog
from projects.models import Project, Semester


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
