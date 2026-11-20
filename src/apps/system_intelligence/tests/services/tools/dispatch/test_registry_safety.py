import json

from agents.tool_context import ToolContext
from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin
from apps.system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
    SystemIntelligenceExport,
)
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.engine.tool_access import DYNAMIC_TOOLS, STATIC_TOOL_GRANTS, TOOL_DENIED
from apps.system_intelligence.services.agents.definition.agent_builder import build_agent_tools
from apps.system_intelligence.services.agents.definition.constants import EXPORT_TOOL_NAMES, WRITE_TOOL_NAMES
from apps.system_intelligence.services.query_tools import TOOL_REGISTRY, execute_tool
from apps.system_intelligence.services.tools.framework.registry import get_agent_tool_callables

READ_TOOL_NAMES = frozenset(
    {
        "search_members",
        "count_members",
        "search_events",
        "get_event_registrations",
        "search_projects",
        "search_email_campaigns",
        "get_campaign_stats",
        "search_cms_pages",
        "search_news",
        "get_page_views",
        "get_checkin_stats",
        "search_semesters",
        "run_custom_query",
        "list_database_models",
        "get_model_schema",
        "get_record",
        "search_records",
        "get_cms_page_detail",
        "get_member_detail",
        "search_contact_info",
        "get_member_activity_summary",
        "get_event_detail",
        "search_event_registrations",
        "get_registration_detail",
        "get_ticket_capacity_summary",
        "get_checkin_breakdown",
        "get_event_question_summary",
        "get_project_detail",
        "get_semester_project_summary",
        "get_current_project_schedule",
        "get_campaign_recipient_logs",
        "get_failed_recipient_report",
        "get_page_view_summary",
        "get_top_paths",
        "get_page_view_trend",
        "search_menus",
        "get_menu_detail",
        "get_footer_content_detail",
        "get_site_settings_detail",
        "search_cms_assets",
        "get_news_source_detail",
    }
)


class SystemIntelligenceToolRegistrySafetyTests(SimpleTestCase):
    def test_every_registered_tool_is_classified(self):
        registered = {tool.__name__ for tool in get_agent_tool_callables()}
        classified = READ_TOOL_NAMES | WRITE_TOOL_NAMES | EXPORT_TOOL_NAMES
        unclassified = registered - classified
        self.assertFalse(
            unclassified,
            (
                f"Unclassified system-intelligence tools detected: {sorted(unclassified)}. "
                "Add each to READ_TOOL_NAMES, WRITE_TOOL_NAMES (in "
                "apps.system_intelligence.services.agents.definition.constants), or EXPORT_TOOL_NAMES "
                "based on whether the tool reads, proposes a human-approved write, or "
                "generates a download. Tools that mutate user data outside the "
                "propose/approve flow MUST NOT be added."
            ),
        )

    def test_classification_sets_are_disjoint(self):
        self.assertFalse(READ_TOOL_NAMES & WRITE_TOOL_NAMES)
        self.assertFalse(READ_TOOL_NAMES & EXPORT_TOOL_NAMES)
        self.assertFalse(WRITE_TOOL_NAMES & EXPORT_TOOL_NAMES)

    def test_all_agent_and_legacy_tools_have_an_access_policy(self):
        agent_tools = {tool.__name__ for tool in get_agent_tool_callables()}
        self.assertEqual(agent_tools, STATIC_TOOL_GRANTS.keys() | DYNAMIC_TOOLS)
        self.assertLessEqual(TOOL_REGISTRY.keys(), agent_tools)

    def test_plan_mode_strips_all_write_tools(self):
        plan_tools = {tool.__name__ for tool in get_agent_tool_callables(include_writes=False)}
        self.assertFalse(plan_tools & WRITE_TOOL_NAMES)

    def test_agent_read_only_mode_strips_export_tools(self):
        read_only_tools = {
            tool.__name__ for tool in get_agent_tool_callables(include_writes=False, include_exports=False)
        }
        self.assertFalse(read_only_tools & WRITE_TOOL_NAMES)
        self.assertFalse(read_only_tools & EXPORT_TOOL_NAMES)


class AssistantToolAuthorizationTests(TransactionTestCase):
    def setUp(self):
        self.user = make_admin(apps=["system_intelligence", "authn"])
        self.conversation = ChatConversation.objects.create(created_by=self.user)
        tokens = actions.set_action_context(str(self.conversation.pk), str(self.user.pk))
        self.addCleanup(actions.reset_action_context, tokens)
        self.tools = {tool.name: tool for tool in build_agent_tools()}

    def invoke(self, name, **params):
        arguments = json.dumps(params)
        context = ToolContext(context=None, tool_name=name, tool_call_id="test-call", tool_arguments=arguments)
        return async_to_sync(self.tools[name].on_invoke_tool)(context, arguments)

    def test_agent_tools_check_all_target_grants_and_track_allowed_usage(self):
        for name, params in (
            ("get_member_detail", {"member_id": str(self.user.pk)}),
            ("search_records", {"app_label": "cms", "model_name": "NewsFeedSource"}),
            ("propose_cms_page_update", {}),
            ("export_news_to_excel", {}),
        ):
            with self.subTest(tool=name):
                self.assertEqual(self.invoke(name, **params), {"result": TOOL_DENIED})
        self.assertFalse(SystemIntelligenceExport.objects.exists())
        self.assertFalse(SystemIntelligenceActionRequest.objects.exists())
        self.assertIn("Count:", self.invoke("count_members")["result"])
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.required_tool_apps, ["authn"])

    def test_legacy_dispatch_requires_explicit_actor_and_target_grant(self):
        call = {"name": "search_semesters", "input": {}}
        self.assertEqual(execute_tool(call), TOOL_DENIED)
        self.assertEqual(execute_tool(call, user=self.user), TOOL_DENIED)

    def test_legacy_dispatch_uses_current_grants_for_an_existing_actor(self):
        call = {"name": "count_members", "input": {}}
        self.assertIn("Count:", execute_tool(call, user=self.user))
        type(self.user).objects.filter(pk=self.user.pk).update(admin_apps=["system_intelligence"])
        self.assertEqual(execute_tool(call, user=self.user), TOOL_DENIED)

    def test_revoked_grant_blocks_new_history_but_owner_can_delete(self):
        self.invoke("count_members")
        self.user.admin_apps = ["system_intelligence"]
        self.user.save(update_fields=["admin_apps"])
        self.client.force_login(self.user)
        detail = reverse("admin:system_intelligence_detail", args=[self.conversation.pk])
        self.assertEqual(self.client.get(detail).status_code, 403)
        delete = reverse("admin:system_intelligence_delete", args=[self.conversation.pk])
        self.assertEqual(self.client.post(delete).status_code, 200)

    def test_historical_chat_is_visible_but_cannot_send_or_retry(self):
        self.conversation.required_tool_apps = None
        self.conversation.save(update_fields=["required_tool_apps"])
        ChatMessage.objects.create(conversation=self.conversation, role="assistant", content="Archived answer")
        self.client.force_login(self.user)
        detail = reverse("admin:system_intelligence_detail", args=[self.conversation.pk])
        response = self.client.get(detail)
        self.assertContains(response, "Archived answer")
        self.assertTrue(response.json()["read_only"])
        for action, body in (("send", {"message": "Hello"}), ("command", {"command": "retry"})):
            url = reverse(f"admin:system_intelligence_{action}", args=[self.conversation.pk])
            self.assertEqual(self.client.post(url, body, content_type="application/json").status_code, 409)
        self.assertEqual(self.conversation.messages.count(), 1)
