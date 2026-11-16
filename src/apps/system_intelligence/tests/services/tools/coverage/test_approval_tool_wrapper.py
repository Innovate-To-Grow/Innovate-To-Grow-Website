import asyncio
import datetime

from django.core.cache import cache
from django.test import TransactionTestCase
from django.utils import timezone

from apps.cms.models import (
    NewsArticle,
)
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_superuser,
)
from apps.projects.models import Project, Semester
from apps.system_intelligence.models import (
    ChatConversation,
    SystemIntelligenceExport,
)
from apps.system_intelligence.services import actions
from apps.system_intelligence.services import tools as si_tools
from apps.system_intelligence.services.tools import exports as exports_module


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
