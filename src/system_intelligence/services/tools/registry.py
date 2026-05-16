from .approval_tools import (
    get_cms_page_detail,
    get_model_schema,
    get_record,
    list_database_models,
    propose_campaign_update,
    propose_cms_page_update,
    propose_db_create,
    propose_db_delete,
    propose_db_update,
    propose_event_update,
    propose_member_update,
    propose_menu_update,
    propose_project_update,
    search_records,
)
from .cms import (
    get_footer_content_detail,
    get_menu_detail,
    get_news_source_detail,
    get_site_settings_detail,
    get_style_sheet_detail,
    search_cms_assets,
    search_menus,
    search_style_sheets,
)
from .domains.analytics import get_page_view_summary, get_page_view_trend, get_top_paths
from .domains.mail import get_campaign_recipient_logs, get_failed_recipient_report
from .domains.members import get_member_activity_summary, get_member_detail, search_contact_info
from .domains.projects import get_current_project_schedule, get_project_detail, get_semester_project_summary
from .events import (
    get_checkin_breakdown,
    get_event_detail,
    get_event_question_summary,
    get_registration_detail,
    get_ticket_capacity_summary,
    search_event_registrations,
)
from .exports import (
    export_events_to_excel,
    export_members_to_excel,
    export_news_to_excel,
    export_projects_to_excel,
    export_records_to_excel,
)
from .legacy import (
    count_members,
    get_campaign_stats,
    get_checkin_stats,
    get_event_registrations,
    get_page_views,
    run_custom_query,
    search_cms_pages,
    search_email_campaigns,
    search_events,
    search_members,
    search_news,
    search_projects,
    search_semesters,
)


def get_adk_tools(*, include_writes: bool = True, include_exports: bool = True) -> list:
    """Return callable tools for Google ADK agent construction.

    When ``include_writes`` is ``False`` (e.g. plan mode), the propose_* and
    other DB-mutating tools are removed entirely so the agent cannot invoke
    them even if the system prompt fails to dissuade it. ``include_exports`` is
    separate because exports generate files but do not mutate domain records.
    """
    from system_intelligence.services.adk.constants import EXPORT_TOOL_NAMES, WRITE_TOOL_NAMES

    tools = [
        search_members,
        count_members,
        get_member_detail,
        search_contact_info,
        get_member_activity_summary,
        search_events,
        get_event_registrations,
        get_event_detail,
        search_event_registrations,
        get_registration_detail,
        get_ticket_capacity_summary,
        get_checkin_breakdown,
        get_event_question_summary,
        search_projects,
        get_project_detail,
        get_semester_project_summary,
        get_current_project_schedule,
        search_email_campaigns,
        get_campaign_stats,
        get_campaign_recipient_logs,
        get_failed_recipient_report,
        search_cms_pages,
        search_news,
        search_menus,
        get_menu_detail,
        get_footer_content_detail,
        get_site_settings_detail,
        search_style_sheets,
        get_style_sheet_detail,
        search_cms_assets,
        get_news_source_detail,
        get_page_views,
        get_checkin_stats,
        get_page_view_summary,
        get_top_paths,
        get_page_view_trend,
        search_semesters,
        run_custom_query,
        list_database_models,
        get_model_schema,
        get_record,
        search_records,
        get_cms_page_detail,
        propose_cms_page_update,
        propose_member_update,
        propose_event_update,
        propose_project_update,
        propose_campaign_update,
        propose_menu_update,
        propose_db_create,
        propose_db_update,
        propose_db_delete,
        export_records_to_excel,
        export_members_to_excel,
        export_events_to_excel,
        export_projects_to_excel,
        export_news_to_excel,
    ]
    if not include_writes:
        tools = [tool for tool in tools if tool.__name__ not in WRITE_TOOL_NAMES]
    if not include_exports:
        tools = [tool for tool in tools if tool.__name__ not in EXPORT_TOOL_NAMES]
    return tools


def get_adk_tool_metadata() -> list[dict[str, str]]:
    """Return simple tool metadata for the admin info panel."""
    return [
        {
            "name": tool.__name__,
            "description": (tool.__doc__ or "").strip().splitlines()[0] if tool.__doc__ else "",
        }
        for tool in get_adk_tools()
    ]
