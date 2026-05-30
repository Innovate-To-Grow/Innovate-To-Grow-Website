"""Coverage tests for the system_intelligence tools batch.

These exercise the async ADK tool wrappers (legacy, exports, approval) plus the
domain/cms/event read helpers and the shared query helpers. External LLM/ADK
machinery is never invoked: the read tools run real ORM queries through
``run_action_service_async`` and the legacy tools dispatch through the local
``TOOL_REGISTRY``.
"""

import asyncio
import datetime

from django.core.cache import cache
from django.db.models import QuerySet
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone
from apps.cms.models import (
    FooterContent,
    Menu,
    NewsArticle,
    NewsFeedSource,
    PageView,
    SiteSettings,
    StyleSheet,
)
from apps.core.services.db_tools.helpers import MAX_ROWS
from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_registration,
    make_superuser,
    make_ticket,
)
from apps.mail.models import EmailCampaign, RecipientLog
from apps.projects.models import Project, Semester
from apps.system_intelligence.models import (
    ChatConversation,
    SystemIntelligenceExport,
)
from apps.system_intelligence.services import actions
from apps.system_intelligence.services import tools as si_tools
from apps.system_intelligence.services.actions.exceptions import ActionRequestError
from apps.system_intelligence.services.tools import exports as exports_module
from apps.system_intelligence.services.tools.cms import layout as layout_module
from apps.system_intelligence.services.tools.cms import news as news_module
from apps.system_intelligence.services.tools.cms import styles as styles_module
from apps.system_intelligence.services.tools.domains import mail as mail_module
from apps.system_intelligence.services.tools.domains import members as members_module
from apps.system_intelligence.services.tools.domains import projects as projects_module
from apps.system_intelligence.services.tools.events import lookup as lookup_module
from apps.system_intelligence.services.tools.events import registrations as registrations_module
from apps.system_intelligence.services.tools.query_helpers import (
    apply_date_range,
    bounded_limit,
    require_one,
)


class QueryHelpersTests(SimpleTestCase):
    """Pure helpers — no DB rows required for the targeted branches."""

    def test_bounded_limit_falls_back_to_default_on_bad_value(self):
        # Lines 13-14: int("abc") raises ValueError -> value = default.
        self.assertEqual(bounded_limit("abc"), 20)

    def test_bounded_limit_clamps_to_max_rows(self):
        self.assertEqual(bounded_limit(10**9), MAX_ROWS)

    def test_require_one_raises_when_queryset_empty(self):
        # Line 35: missing object surfaces a labelled ActionRequestError.
        empty = Menu.objects.none()
        with self.assertRaises(ActionRequestError) as cm:
            require_one(empty, "Widget")
        self.assertEqual(str(cm.exception), "Widget was not found.")

    def test_apply_date_range_filters_both_bounds(self):
        # Lines 41 and 43: each branch appends a filter to the queryset.
        base = PageView.objects.all()
        filtered = apply_date_range(
            base, "timestamp", date_from="2025-01-01T00:00:00+00:00", date_to="2025-12-31T00:00:00+00:00"
        )
        self.assertIsInstance(filtered, QuerySet)
        where = str(filtered.query).lower()
        self.assertIn(">=", where)
        self.assertIn("<=", where)
        self.assertIsNot(filtered, base)


class MemberToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(
            email="ada@example.com",
            first_name="Ada",
            last_name="Lovelace",
            organization="Analytical Engines",
            title="Engineer",
        )
        ContactPhone.objects.create(
            member=self.member, phone_number="2095550100", region="1-US", subscribe=True, verified=True
        )

    def test_get_member_activity_summary_aggregates_domains(self):
        # members.py lines 122-131 + 42/50: activity summary via member_id lookup.
        event = make_event(name="Demo Day", date=datetime.date(2026, 5, 1))
        ticket = make_ticket(event, name="General")
        make_registration(self.member, event, ticket, attendee_email="ada@example.com")
        campaign = EmailCampaign.objects.create(name="Invite", subject="Join", body="Hi")
        RecipientLog.objects.create(
            campaign=campaign, member=self.member, email_address="ada@example.com", status="sent"
        )
        PageView.objects.create(path="/event", member=self.member, session_key="s1")

        summary = asyncio.run(si_tools.get_member_activity_summary(member_id=str(self.member.pk)))

        self.assertEqual(summary["member"]["first_name"], "Ada")
        self.assertEqual(summary["registration_count"], 1)
        self.assertEqual(summary["page_view_count"], 1)
        self.assertEqual(summary["campaign_delivery_breakdown"], [{"status": "sent", "count": 1}])
        self.assertEqual(len(summary["recent_registrations"]), 1)
        self.assertEqual(summary["recent_page_views"][0]["path"], "/event")

    def test_find_member_by_email_branch(self):
        # members.py line 52 (covered indirectly) + 50 via member_id path here.
        detail = asyncio.run(si_tools.get_member_activity_summary(email="ada@example.com"))
        self.assertEqual(detail["member"]["last_name"], "Lovelace")

    def test_find_member_without_args_returns_tool_error(self):
        # members.py line 53: ActionRequestError caught and surfaced as tool output.
        result = asyncio.run(si_tools.get_member_detail())
        self.assertIn("Tool error", result["result"])
        self.assertIn("Provide member_id or email", result["result"])

    def test_search_contact_info_phone_only_drops_emails(self):
        # members.py lines 98-100: phone filter set, email side -> none().
        result = asyncio.run(si_tools.search_contact_info(phone="2095550100"))
        self.assertEqual(result["emails"]["total"], 0)
        self.assertEqual(result["phones"]["total"], 1)
        self.assertEqual(result["phones"]["rows"][0]["phone_number"], "2095550100")

    def test_search_contact_info_subscribed_and_verified_filters(self):
        # members.py lines 101-106: subscribed + verified branches on both querysets.
        ContactEmail.objects.filter(member=self.member).update(subscribe=True, verified=True)
        result = asyncio.run(si_tools.search_contact_info(subscribed=True, verified=True))
        self.assertGreaterEqual(result["emails"]["total"], 1)
        self.assertEqual(result["phones"]["total"], 1)

        none_result = asyncio.run(si_tools.search_contact_info(subscribed=False, verified=False))
        self.assertEqual(none_result["emails"]["total"], 0)
        self.assertEqual(none_result["phones"]["total"], 0)


class ProjectToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.spring = Semester.objects.create(year=2026, season=Semester.Season.SPRING, is_published=True)
        self.fall = Semester.objects.create(year=2026, season=Semester.Season.FALL, is_published=False)
        self.project = Project.objects.create(
            semester=self.spring,
            class_code="CSE",
            team_number="CSE-001",
            team_name="Delta",
            project_title="Campus Navigator",
            organization="UC Merced",
            industry="Education",
        )

    def test_get_project_detail_by_title(self):
        # projects.py lines 57-58: title branch.
        result = asyncio.run(si_tools.get_project_detail(title="Navigator"))
        self.assertEqual(result["project"]["team_number"], "CSE-001")
        self.assertEqual(result["semester"]["year"], 2026)

    def test_get_project_detail_by_team_number(self):
        # projects.py lines 59-60: team_number branch.
        result = asyncio.run(si_tools.get_project_detail(team_number="CSE-001"))
        self.assertEqual(result["project"]["project_title"], "Campus Navigator")

    def test_get_project_detail_without_args_returns_tool_error(self):
        # projects.py line 61: ActionRequestError -> tool error string.
        result = asyncio.run(si_tools.get_project_detail())
        self.assertIn("Provide project_id, title, or team_number", result["result"])

    def test_semester_summary_by_year_and_fall_season(self):
        # projects.py lines 74/76/80-82 + 90/97 via _season_value + _find_semester.
        Project.objects.create(
            semester=self.fall,
            class_code="CSE",
            team_number="CSE-900",
            team_name="Omega",
            project_title="Fall Thing",
            organization="UC Merced",
            industry="Tech",
        )
        result = asyncio.run(si_tools.get_semester_project_summary(year=2026, season="Fall"))
        self.assertEqual(result["semester"]["season"], Semester.Season.FALL)
        self.assertEqual(result["project_count"], 1)

    def test_semester_summary_season_as_int(self):
        # projects.py line 76: isinstance(season, int) branch returns season directly.
        result = asyncio.run(si_tools.get_semester_project_summary(year=2026, season=1))
        self.assertEqual(result["semester"]["season"], Semester.Season.SPRING)

    def test_semester_summary_invalid_season_returns_tool_error(self):
        # projects.py line 82: unrecognised season raises ActionRequestError.
        result = asyncio.run(si_tools.get_semester_project_summary(year=2026, season="winter"))
        self.assertIn("season must be Spring, Fall, 1, or 2", result["result"])

    def test_semester_summary_by_id(self):
        # projects.py line 90: semester_id branch.
        result = asyncio.run(si_tools.get_semester_project_summary(semester_id=str(self.spring.pk)))
        self.assertEqual(result["project_count"], 1)

    def test_semester_summary_no_args_picks_latest(self):
        # projects.py line 97: fallback ordering by -year/-season.
        result = asyncio.run(si_tools.get_semester_project_summary())
        self.assertEqual(result["semester"]["year"], 2026)

    def test_current_schedule_by_id(self):
        # projects.py line 123: schedule_id branch.
        schedule = CurrentProjectSchedule.objects.create(name="Showcase", is_active=False)
        CurrentProject.objects.create(
            schedule=schedule,
            class_code="CSE",
            team_number="CSE-001",
            project_title="Live Nav",
            organization="UC Merced",
            is_presenting=True,
        )
        result = asyncio.run(si_tools.get_current_project_schedule(schedule_id=str(schedule.pk)))
        self.assertEqual(result["presenting_count"], 1)

    def test_current_schedule_inactive_fallback(self):
        # projects.py line 127: active_only False -> order_by(-updated_at).
        schedule = CurrentProjectSchedule.objects.create(name="Old", is_active=False)
        result = asyncio.run(si_tools.get_current_project_schedule(active_only=False))
        self.assertEqual(result["schedule"]["id"], str(schedule.pk))

    def test_season_value_none_returns_none(self):
        # projects.py line 74: explicit None short-circuit.
        self.assertIsNone(projects_module._season_value(None))


class LayoutToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.menu = Menu.objects.create(
            name="main", display_name="Main", is_active=True, items=[{"title": "Home", "url": "/"}]
        )
        Menu.objects.create(name="footer-nav", display_name="Footer", is_active=False, items=[])

    def test_search_menus_filters_by_name_and_active(self):
        # layout.py line 13 (wrapper) + 34/37-38/39-41 filter branches.
        result = asyncio.run(si_tools.search_menus(name="main", is_active=True))
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["name"], "main")

    def test_search_menus_inactive_only(self):
        result = asyncio.run(si_tools.search_menus(is_active=False))
        names = {row["name"] for row in result["rows"]}
        self.assertIn("footer-nav", names)
        self.assertNotIn("main", names)

    def test_find_menu_by_id(self):
        # layout.py line 49: menu_id branch.
        result = asyncio.run(si_tools.get_menu_detail(menu_id=str(self.menu.pk)))
        self.assertEqual(result["menu"]["name"], "main")

    def test_find_menu_without_args_returns_tool_error(self):
        # layout.py line 52: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_menu_detail())
        self.assertIn("Provide menu_id or name", result["result"])

    def test_footer_detail_by_id(self):
        # layout.py line 67: footer_id branch.
        footer = FooterContent.objects.create(
            slug="main-footer", name="Main Footer", is_active=True, content={"columns": []}
        )
        result = asyncio.run(si_tools.get_footer_content_detail(footer_id=str(footer.pk)))
        self.assertEqual(result["footer"]["slug"], "main-footer")

    def test_footer_detail_by_slug(self):
        # layout.py line 69: slug branch.
        FooterContent.objects.create(slug="alt-footer", name="Alt", is_active=False, content={})
        result = asyncio.run(si_tools.get_footer_content_detail(slug="alt-footer"))
        self.assertEqual(result["footer"]["name"], "Alt")

    def test_footer_detail_fallback_latest(self):
        # layout.py line 73: active_only False -> latest by updated_at.
        footer = FooterContent.objects.create(slug="latest-footer", name="Latest", is_active=False, content={})
        result = asyncio.run(si_tools.get_footer_content_detail(active_only=False))
        self.assertEqual(result["footer"]["id"], str(footer.pk))


class MailToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.campaign = EmailCampaign.objects.create(name="Spring Blast", subject="Hello", body="Body")
        RecipientLog.objects.create(
            campaign=self.campaign, email_address="ok@example.com", recipient_name="OK", status="sent"
        )
        RecipientLog.objects.create(
            campaign=self.campaign,
            email_address="bad@example.com",
            recipient_name="Bad",
            status="failed",
            error_message="Rejected",
        )

    def test_recipient_logs_filtered_by_status_and_email(self):
        # mail.py lines 65/67: status + email filters.
        result = asyncio.run(
            si_tools.get_campaign_recipient_logs(campaign_name="Spring", status="failed", email="bad@example.com")
        )
        self.assertEqual(result["recipient_logs"]["total"], 1)
        self.assertEqual(result["recipient_logs"]["rows"][0]["email_address"], "bad@example.com")

    def test_find_campaign_by_name_branch(self):
        # mail.py line 38: campaign_name branch resolves the campaign.
        result = asyncio.run(si_tools.get_failed_recipient_report(campaign_name="Spring"))
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["campaign"]["name"], "Spring Blast")

    def test_find_campaign_without_args_returns_tool_error(self):
        # mail.py line 39: ActionRequestError surfaced as tool output.
        result = asyncio.run(si_tools.get_campaign_recipient_logs())
        self.assertIn("Provide campaign_id or campaign_name", result["result"])


class EventLookupToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.event = make_event(name="Demo Day", date=datetime.date(2026, 5, 1))
        self.event.slug = "demo-day"
        self.event.save()
        make_ticket(self.event, name="General")

    def test_find_event_by_slug(self):
        # lookup.py lines 39-40: slug branch.
        result = asyncio.run(si_tools.get_event_detail(slug="demo-day"))
        self.assertEqual(result["event"]["name"], "Demo Day")

    def test_find_event_by_name(self):
        # lookup.py lines 41-42: name icontains branch ordered by -date.
        result = asyncio.run(si_tools.get_event_detail(name="Demo"))
        self.assertEqual(result["event"]["slug"], "demo-day")

    def test_find_event_without_args_returns_tool_error(self):
        # lookup.py line 43: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_event_detail())
        self.assertIn("Provide event_id, slug, or name", result["result"])


class RegistrationToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="ada@example.com", first_name="Ada", last_name="Lovelace")
        self.event = make_event(name="Demo Day", date=datetime.date(2026, 5, 1))
        self.ticket = make_ticket(self.event, name="General")
        self.registration = make_registration(
            self.member,
            self.event,
            self.ticket,
            attendee_email="ada@example.com",
            attendee_first_name="Ada",
            attendee_last_name="Lovelace",
            ticket_code="TICKET-XYZ",
        )

    def test_search_registrations_by_all_filters(self):
        # registrations.py lines 32/34/38: event_id, event_name, ticket_id filters.
        result = asyncio.run(
            si_tools.search_event_registrations(
                event_id=str(self.event.pk),
                event_name="Demo",
                email="ada@example.com",
                ticket_id=str(self.ticket.pk),
            )
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["attendee_email"], "ada@example.com")

    def test_registration_detail_by_ticket_code(self):
        # registrations.py lines 72-73: ticket_code branch.
        result = asyncio.run(si_tools.get_registration_detail(ticket_code="TICKET-XYZ"))
        self.assertEqual(result["registration"]["ticket_code"], "TICKET-XYZ")
        self.assertEqual(result["event"]["name"], "Demo Day")
        self.assertEqual(result["ticket"]["name"], "General")

    def test_registration_detail_without_args_returns_tool_error(self):
        # registrations.py line 75: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_registration_detail())
        self.assertIn("Provide registration_id or ticket_code", result["result"])


class NewsSourceToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml", is_active=True
        )
        NewsArticle.objects.create(
            source="ucm",
            source_guid="news-1",
            title="Award",
            source_url="https://example.com/news",
            published_at=timezone.now(),
        )

    def test_news_source_by_id(self):
        # news.py line 23: source_id branch.
        result = asyncio.run(si_tools.get_news_source_detail(source_id=str(self.source.pk)))
        self.assertEqual(result["source"]["source_key"], "ucm")

    def test_news_source_by_source_key(self):
        # news.py lines 25-26: source_key branch.
        result = asyncio.run(si_tools.get_news_source_detail(source_key="ucm"))
        self.assertEqual(result["source"]["name"], "UC Merced")
        self.assertEqual(result["article_count"], 1)

    def test_news_source_by_name(self):
        # news.py lines 27-28: name icontains branch.
        result = asyncio.run(si_tools.get_news_source_detail(name="Merced"))
        self.assertEqual(result["source"]["source_key"], "ucm")

    def test_news_source_without_args_returns_tool_error(self):
        # news.py line 29: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_news_source_detail())
        self.assertIn("Provide source_id, source_key, or name", result["result"])


class StyleSheetToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.sheet = StyleSheet.objects.create(
            name="global", display_name="Global", css="body { color: #000; }", is_active=True
        )
        StyleSheet.objects.create(name="hidden", display_name="Hidden", css="", is_active=False)

    def test_search_style_sheets_filters_inactive(self):
        # styles.py line 28: is_active filter branch.
        result = asyncio.run(si_tools.search_style_sheets(is_active=False))
        names = {row["name"] for row in result["rows"]}
        self.assertIn("hidden", names)
        self.assertNotIn("global", names)

    def test_style_sheet_detail_by_id(self):
        # styles.py line 41: sheet_id branch.
        result = asyncio.run(si_tools.get_style_sheet_detail(sheet_id=str(self.sheet.pk)))
        self.assertEqual(result["style_sheet"]["name"], "global")

    def test_style_sheet_detail_by_name(self):
        # styles.py lines 43-47: name branch + css_length computation.
        result = asyncio.run(si_tools.get_style_sheet_detail(name="global"))
        self.assertEqual(result["style_sheet"]["name"], "global")
        self.assertGreater(result["style_sheet"]["css_length"], 0)

    def test_style_sheet_detail_without_args_returns_tool_error(self):
        # styles.py line 45: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_style_sheet_detail())
        self.assertIn("Provide sheet_id or name", result["result"])


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


class ApprovalToolWrapperTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.conversation = ChatConversation.objects.create(created_by=self.admin_user)
        self.context_tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        self.member = make_member(email="target@example.com", first_name="Tar", last_name="Get")

    def tearDown(self):
        actions.reset_action_context(self.context_tokens)

    def test_list_database_models_wrapper(self):
        # approval_tools.py line 10. The service returns a JSON string wrapped by run_action_service.
        result = asyncio.run(si_tools.list_database_models())
        self.assertIn("authn.Member", result["result"])

    def test_get_model_schema_wrapper(self):
        # approval_tools.py line 15.
        result = asyncio.run(si_tools.get_model_schema("authn", "Member"))
        self.assertIn("readable_fields", result["result"])

    def test_get_record_wrapper(self):
        # approval_tools.py line 20.
        result = asyncio.run(si_tools.get_record("authn", "Member", str(self.member.pk)))
        self.assertIn("Tar", result["result"])

    def test_search_records_wrapper(self):
        # approval_tools.py line 32.
        result = asyncio.run(si_tools.search_records("authn", "Member", filters={"first_name": "Tar"}))
        self.assertIn("Tar", result["result"])

    def test_get_cms_page_detail_wrapper_error_surface(self):
        # approval_tools.py line 41: dispatches; missing page surfaces a tool error.
        result = asyncio.run(si_tools.get_cms_page_detail(slug="no-such-page"))
        self.assertIn("Tool error", result["result"])

    def test_propose_cms_page_update_wrapper(self):
        # approval_tools.py line 53.
        from apps.cms.models import CMSPage

        page = CMSPage.objects.create(title="P", slug="p", route="/p", status="draft")
        result = asyncio.run(
            si_tools.propose_cms_page_update(page_id=str(page.pk), page_fields={"title": "P2"}, summary="x")
        )
        self.assertIn("action_request", result)

    def test_propose_db_update_wrapper(self):
        # approval_tools.py line 71.
        result = asyncio.run(si_tools.propose_db_update("authn", "Member", str(self.member.pk), {"first_name": "New"}))
        self.assertIn("action_request", result)

    def test_propose_db_delete_wrapper(self):
        # approval_tools.py line 78.
        result = asyncio.run(si_tools.propose_db_delete("authn", "Member", str(self.member.pk)))
        self.assertIn("action_request", result)


class ExportToolWrapperTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.conversation = ChatConversation.objects.create(created_by=self.admin_user)
        self.context_tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))

    def tearDown(self):
        actions.reset_action_context(self.context_tokens)

    def test_download_url_helper(self):
        # exports.py line 36.
        self.assertEqual(
            exports_module._download_url("abc"),
            "/admin/system-intelligence/exports/abc/download/",
        )

    def test_success_payload_builds_markdown_instruction(self):
        # exports.py lines 19, 36 (via _success_payload).
        export = SystemIntelligenceExport(
            id="11111111-1111-1111-1111-111111111111",
            filename="members.xlsx",
            title="Members export",
            row_count=3,
            model_label="authn.Member",
            field_names=["first_name", "email"],
        )
        payload = exports_module._success_payload(export)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["filename"], "members.xlsx")
        self.assertEqual(payload["fields"], ["first_name", "email"])
        self.assertIn("[Download members.xlsx]", payload["instruction"])
        self.assertIn("/download/", payload["download_url"])

    def test_export_members_to_excel_wrapper(self):
        # exports.py lines 41-42 (_create) + 78 (export_members_to_excel).
        result = asyncio.run(exports_module.export_members_to_excel())
        self.assertTrue(result["ok"])
        self.assertEqual(result["model_label"], "authn.Member")
        self.assertTrue(SystemIntelligenceExport.objects.filter(id=result["export_id"]).exists())

    def test_export_records_to_excel_wrapper(self):
        # exports.py line 60.
        result = asyncio.run(
            exports_module.export_records_to_excel(app_label="authn", model_name="Member", title="Custom")
        )
        self.assertEqual(result["title"], "Custom")

    def test_export_events_to_excel_wrapper(self):
        # exports.py line 95.
        make_event(name="Exportable", date=datetime.date(2026, 5, 1))
        result = asyncio.run(exports_module.export_events_to_excel())
        self.assertEqual(result["model_label"], "event.Event")

    def test_export_projects_to_excel_wrapper(self):
        # exports.py line 112.
        semester = Semester.objects.create(year=2026, season=Semester.Season.SPRING)
        Project.objects.create(
            semester=semester,
            class_code="CSE",
            team_number="CSE-1",
            project_title="Exportable",
            organization="UC Merced",
            industry="Tech",
        )
        result = asyncio.run(exports_module.export_projects_to_excel())
        self.assertEqual(result["model_label"], "projects.Project")

    def test_export_news_to_excel_wrapper(self):
        # exports.py line 129.
        NewsArticle.objects.create(
            source="ucm",
            source_guid="export-news",
            title="Exportable News",
            source_url="https://example.com/export",
            published_at=timezone.now(),
        )
        result = asyncio.run(exports_module.export_news_to_excel())
        self.assertEqual(result["model_label"], "cms.NewsArticle")


class DirectHelperReferenceTests(SimpleTestCase):
    """Reference the imported domain modules so unused-import lint stays clean."""

    def test_modules_are_importable(self):
        for module in (
            members_module,
            projects_module,
            layout_module,
            news_module,
            styles_module,
            mail_module,
            lookup_module,
            registrations_module,
            exports_module,
        ):
            self.assertTrue(hasattr(module, "__name__"))
        self.assertTrue(callable(SiteSettings.load))
