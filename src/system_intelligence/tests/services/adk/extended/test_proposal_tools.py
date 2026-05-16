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
from system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest
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

    def test_typed_proposal_wrappers_create_pending_actions_and_apply_only_after_approval(self):
        data = self._make_sample_operational_data()
        proposals = [
            (
                "member",
                data["member"],
                lambda: data["member"].title,
                system_intelligence_tools.propose_member_update(str(data["member"].pk), {"title": "Updated Title"}),
                "Updated Title",
            ),
            (
                "event",
                data["event"],
                lambda: data["event"].location,
                system_intelligence_tools.propose_event_update(str(data["event"].pk), {"location": "Updated Hall"}),
                "Updated Hall",
            ),
            (
                "project",
                data["project"],
                lambda: data["project"].project_title,
                system_intelligence_tools.propose_project_update(
                    str(data["project"].pk), {"project_title": "Updated Navigator"}
                ),
                "Updated Navigator",
            ),
            (
                "campaign",
                data["campaign"],
                lambda: data["campaign"].subject,
                system_intelligence_tools.propose_campaign_update(
                    str(data["campaign"].pk), {"subject": "Updated Subject"}
                ),
                "Updated Subject",
            ),
            (
                "menu",
                data["menu"],
                lambda: data["menu"].display_name,
                system_intelligence_tools.propose_menu_update(str(data["menu"].pk), {"display_name": "Updated Menu"}),
                "Updated Menu",
            ),
        ]

        for label, obj, current_value, coroutine, expected_value in proposals:
            before = current_value()
            response = asyncio.run(coroutine)
            obj.refresh_from_db()
            self.assertEqual(current_value(), before, label)
            action = SystemIntelligenceActionRequest.objects.get(id=response["action_request"]["id"])
            self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_PENDING)
            actions.approve_action_request(action.id, self.admin_user)
            obj.refresh_from_db()
            self.assertEqual(current_value(), expected_value, label)

    def test_typed_proposals_preserve_sensitive_model_and_field_denials(self):
        member = make_member(email="security@example.com", first_name="Sec", last_name="User")

        password_result = asyncio.run(
            system_intelligence_tools.propose_member_update(str(member.pk), {"password": "x"})
        )
        self.assertIn("Tool error", password_result["result"])
        self.assertIn("not writable", password_result["result"])

        credential_result = asyncio.run(
            system_intelligence_tools.propose_db_create(
                "core",
                "AWSCredentialConfig",
                {"name": "Bad", "access_key_id": "key", "secret_access_key": "secret"},
            )
        )
        self.assertIn("Tool error", credential_result["result"])
        self.assertIn("Write access is not allowed", credential_result["result"])

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
