from django.test import SimpleTestCase

from system_intelligence.services.adk.constants import EXPORT_TOOL_NAMES, WRITE_TOOL_NAMES
from system_intelligence.services.tools.registry import get_adk_tools

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
        "search_style_sheets",
        "get_style_sheet_detail",
        "search_cms_assets",
        "get_news_source_detail",
    }
)


class SystemIntelligenceToolRegistrySafetyTests(SimpleTestCase):
    def test_every_registered_tool_is_classified(self):
        registered = {tool.__name__ for tool in get_adk_tools()}
        classified = READ_TOOL_NAMES | WRITE_TOOL_NAMES | EXPORT_TOOL_NAMES
        unclassified = registered - classified
        self.assertFalse(
            unclassified,
            (
                f"Unclassified system-intelligence tools detected: {sorted(unclassified)}. "
                "Add each to READ_TOOL_NAMES, WRITE_TOOL_NAMES (in "
                "system_intelligence.services.adk.constants), or EXPORT_TOOL_NAMES "
                "based on whether the tool reads, proposes a human-approved write, or "
                "generates a download. Tools that mutate user data outside the "
                "propose/approve flow MUST NOT be added."
            ),
        )

    def test_classification_sets_are_disjoint(self):
        self.assertFalse(READ_TOOL_NAMES & WRITE_TOOL_NAMES)
        self.assertFalse(READ_TOOL_NAMES & EXPORT_TOOL_NAMES)
        self.assertFalse(WRITE_TOOL_NAMES & EXPORT_TOOL_NAMES)

    def test_plan_mode_strips_all_write_tools(self):
        plan_tools = {tool.__name__ for tool in get_adk_tools(include_writes=False)}
        self.assertFalse(plan_tools & WRITE_TOOL_NAMES)

    def test_adk_web_read_only_mode_strips_export_tools(self):
        read_only_tools = {tool.__name__ for tool in get_adk_tools(include_writes=False, include_exports=False)}
        self.assertFalse(read_only_tools & WRITE_TOOL_NAMES)
        self.assertFalse(read_only_tools & EXPORT_TOOL_NAMES)
