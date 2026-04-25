from .approval_tools import (
    get_cms_page_detail,
    get_model_schema,
    get_record,
    list_database_models,
    propose_cms_page_update,
    propose_db_create,
    propose_db_delete,
    propose_db_update,
    search_records,
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


def get_adk_tools() -> list:
    """Return callable tools for Google ADK agent construction."""
    return [
        search_members,
        count_members,
        search_events,
        get_event_registrations,
        search_projects,
        search_email_campaigns,
        get_campaign_stats,
        search_cms_pages,
        search_news,
        get_page_views,
        get_checkin_stats,
        search_semesters,
        run_custom_query,
        list_database_models,
        get_model_schema,
        get_record,
        search_records,
        get_cms_page_detail,
        propose_cms_page_update,
        propose_db_create,
        propose_db_update,
        propose_db_delete,
    ]


def get_adk_tool_metadata() -> list[dict[str, str]]:
    """Return simple tool metadata for the admin info panel."""
    return [
        {
            "name": tool.__name__,
            "description": (tool.__doc__ or "").strip().splitlines()[0] if tool.__doc__ else "",
        }
        for tool in get_adk_tools()
    ]
