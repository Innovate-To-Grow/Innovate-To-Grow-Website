from django.core.cache import cache
from django.test import TransactionTestCase

from event.tests.helpers import make_superuser
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

    def test_registry_exposes_extended_core_backend_tools(self):
        names = [tool.__name__ for tool in system_intelligence_tools.get_adk_tools()]

        expected = {
            "get_member_detail",
            "search_contact_info",
            "get_event_detail",
            "search_event_registrations",
            "get_project_detail",
            "get_current_project_schedule",
            "get_menu_detail",
            "get_campaign_recipient_logs",
            "get_page_view_summary",
            "propose_member_update",
            "propose_event_update",
            "propose_project_update",
            "propose_campaign_update",
            "propose_menu_update",
        }
        self.assertTrue(expected.issubset(set(names)))
        metadata = {item["name"]: item["description"] for item in system_intelligence_tools.get_adk_tool_metadata()}
        self.assertIn("Get a member profile", metadata["get_member_detail"])
