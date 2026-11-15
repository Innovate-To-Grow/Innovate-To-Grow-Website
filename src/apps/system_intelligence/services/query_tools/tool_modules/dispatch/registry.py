from ..custom import run_custom_query
from ..domains.analytics import get_page_views
from ..domains.cms import search_cms_pages, search_news
from ..domains.events import get_checkin_stats, get_event_registrations, search_events
from ..domains.mail import get_campaign_stats, search_email_campaigns
from ..domains.members import count_members, search_members
from ..domains.projects import search_projects, search_semesters

TOOL_REGISTRY = {
    "search_members": search_members,
    "count_members": count_members,
    "search_events": search_events,
    "get_event_registrations": get_event_registrations,
    "search_projects": search_projects,
    "search_email_campaigns": search_email_campaigns,
    "get_campaign_stats": get_campaign_stats,
    "search_cms_pages": search_cms_pages,
    "search_news": search_news,
    "get_page_views": get_page_views,
    "get_checkin_stats": get_checkin_stats,
    "search_semesters": search_semesters,
    "run_custom_query": run_custom_query,
}
