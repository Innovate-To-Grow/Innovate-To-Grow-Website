import asyncio
import datetime

from django.core.cache import cache
from django.test import TransactionTestCase
from django.utils import timezone

from authn.models import ContactPhone
from cms.models import CMSAsset, FooterContent, Menu, NewsArticle, NewsFeedSource, PageView, SiteSettings, StyleSheet
from event.models import CheckIn, CheckInRecord, CurrentProject, CurrentProjectSchedule, Question
from event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket
from mail.models import EmailCampaign, RecipientLog
from projects.models import Project, Semester
from system_intelligence.models import ChatConversation
from system_intelligence.services import actions
from system_intelligence.services import tools as system_intelligence_tools


class SystemIntelligenceExtendedToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.conversation = ChatConversation.objects.create(created_by=self.admin_user)
        self.context_tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))

    def tearDown(self):
        actions.reset_action_context(self.context_tokens)

    def test_extended_read_tools_cover_core_domains_and_safe_outputs(self):
        data = self._make_sample_operational_data()

        member_detail = asyncio.run(system_intelligence_tools.get_member_detail(email="ada@example.com"))
        self.assertEqual(member_detail["member"]["first_name"], "Ada")
        self.assertNotIn("password", str(member_detail).lower())

        contacts = asyncio.run(system_intelligence_tools.search_contact_info(email="missing@example.com"))
        self.assertEqual(contacts["emails"]["total"], 0)
        self.assertEqual(contacts["phones"]["total"], 0)

        event_detail = asyncio.run(system_intelligence_tools.get_event_detail(event_id=str(data["event"].pk)))
        self.assertEqual(event_detail["counts"]["registrations"], 1)

        registrations = asyncio.run(system_intelligence_tools.search_event_registrations(email="ada@example.com"))
        self.assertEqual(registrations["total"], 1)

        registration_detail = asyncio.run(
            system_intelligence_tools.get_registration_detail(registration_id=str(data["registration"].pk))
        )
        self.assertEqual(registration_detail["registration"]["attendee_email"], "ada@example.com")

        ticket_summary = asyncio.run(
            system_intelligence_tools.get_ticket_capacity_summary(event_id=str(data["event"].pk))
        )
        self.assertEqual(ticket_summary["registration_count"], 1)

        checkins = asyncio.run(system_intelligence_tools.get_checkin_breakdown(event_id=str(data["event"].pk)))
        self.assertEqual(checkins["unique_checked_in"], 1)

        questions = asyncio.run(system_intelligence_tools.get_event_question_summary(event_id=str(data["event"].pk)))
        self.assertEqual(len(questions["questions"]), 1)

        project = asyncio.run(system_intelligence_tools.get_project_detail(project_id=str(data["project"].pk)))
        self.assertEqual(project["project"]["project_title"], "Campus Navigator")

        semester = asyncio.run(system_intelligence_tools.get_semester_project_summary(year=2026, season="Spring"))
        self.assertEqual(semester["project_count"], 1)

        current_schedule = asyncio.run(system_intelligence_tools.get_current_project_schedule())
        self.assertEqual(current_schedule["presenting_count"], 1)

        menu = asyncio.run(system_intelligence_tools.get_menu_detail(name="main"))
        self.assertEqual(menu["menu"]["name"], "main")

        footer = asyncio.run(system_intelligence_tools.get_footer_content_detail(active_only=True))
        self.assertEqual(footer["footer"]["slug"], "main-footer")

        site_settings = asyncio.run(system_intelligence_tools.get_site_settings_detail())
        self.assertIn("colors", site_settings["design_token_groups"])

        style_sheets = asyncio.run(system_intelligence_tools.search_style_sheets(name="tool-global"))
        self.assertEqual(style_sheets["total"], 1)

        style_sheet = asyncio.run(system_intelligence_tools.get_style_sheet_detail(name="tool-global"))
        self.assertGreater(style_sheet["style_sheet"]["css_length"], 0)

        assets = asyncio.run(system_intelligence_tools.search_cms_assets(name="Map"))
        self.assertEqual(assets["total"], 1)

        source = asyncio.run(system_intelligence_tools.get_news_source_detail(source_key="ucm"))
        self.assertEqual(source["article_count"], 1)

        logs = asyncio.run(system_intelligence_tools.get_campaign_recipient_logs(campaign_id=str(data["campaign"].pk)))
        self.assertEqual(logs["recipient_logs"]["total"], 1)

        failures = asyncio.run(
            system_intelligence_tools.get_failed_recipient_report(campaign_id=str(data["campaign"].pk))
        )
        self.assertEqual(failures["failure_count"], 1)

        views = asyncio.run(system_intelligence_tools.get_page_view_summary(path="/event"))
        self.assertEqual(views["total_views"], 1)

        top_paths = asyncio.run(system_intelligence_tools.get_top_paths())
        self.assertEqual(top_paths["rows"][0]["path"], "/event")

        trend = asyncio.run(system_intelligence_tools.get_page_view_trend(granularity="day"))
        self.assertEqual(trend["rows"][0]["views"], 1)

    def _make_sample_operational_data(self):
        member = make_member(
            email="ada@example.com",
            first_name="Ada",
            last_name="Lovelace",
            organization="Analytical Engines",
            title="Engineer",
        )
        ContactPhone.objects.create(member=member, phone_number="2095550100", region="1-US", verified=True)

        event = make_event(name="Demo Day", date=datetime.date(2026, 5, 1), is_live=True)
        ticket = make_ticket(event, name="General")
        Question.objects.create(event=event, text="Dietary restrictions?", is_required=False)
        registration = make_registration(
            member,
            event,
            ticket,
            attendee_email="ada@example.com",
            question_answers=[{"question": "Dietary restrictions?", "answer": "None"}],
        )
        station = CheckIn.objects.create(event=event, name="Main Entrance", is_active=True)
        CheckInRecord.objects.create(check_in=station, registration=registration, scanned_by=self.admin_user)

        semester = Semester.objects.create(year=2026, season=Semester.Season.SPRING, is_published=True)
        project = Project.objects.create(
            semester=semester,
            class_code="CSE",
            team_number="CSE-001",
            team_name="Delta",
            project_title="Campus Navigator",
            organization="UC Merced",
            industry="Education",
            student_names="Ada, Grace",
        )
        schedule = CurrentProjectSchedule.objects.create(name="Spring Showcase", is_active=True)
        CurrentProject.objects.create(
            schedule=schedule,
            class_code="CSE",
            team_number="CSE-001",
            project_title="Live Navigator",
            organization="UC Merced",
            is_presenting=True,
        )

        menu = Menu.objects.create(name="main", display_name="Main", items=[{"title": "Home", "url": "/"}])
        FooterContent.objects.create(slug="main-footer", name="Main Footer", is_active=True, content={"columns": []})
        SiteSettings.load()
        StyleSheet.objects.update_or_create(
            name="tool-global",
            defaults={"display_name": "Tool Global", "css": "body { color: #123; }", "is_active": True},
        )
        CMSAsset.objects.create(name="Map", file="cms/assets/map.pdf")
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml", is_active=True
        )
        NewsArticle.objects.create(
            source=source.source_key,
            source_guid="news-1",
            title="News",
            source_url="https://example.com/news",
            published_at=timezone.now(),
        )

        campaign = EmailCampaign.objects.create(name="Invite", subject="Join us", body="Hello")
        RecipientLog.objects.create(
            campaign=campaign,
            member=member,
            email_address="ada@example.com",
            recipient_name="Ada Lovelace",
            status="failed",
            error_message="Rejected",
        )
        PageView.objects.create(path="/event", member=member, session_key="session-1")

        return {
            "member": member,
            "event": event,
            "registration": registration,
            "project": project,
            "menu": menu,
            "campaign": campaign,
        }
