from typing import Any

from .runtime import run_tool_async


async def search_members(
    name: str | None = None,
    email: str | None = None,
    organization: str | None = None,
    is_staff: bool | None = None,
    is_active: bool | None = None,
):
    """Search members by name, email, organization, staff status, or active status."""
    return await run_tool_async("search_members", locals())


async def count_members(is_staff: bool | None = None, is_active: bool | None = None, organization: str | None = None):
    """Count members with optional staff, active, or organization filters."""
    return await run_tool_async("count_members", locals())


async def search_events(
    name: str | None = None, is_live: bool | None = None, date_from: str | None = None, date_to: str | None = None
):
    """Search events by name, live status, or date range."""
    return await run_tool_async("search_events", locals())


async def get_event_registrations(
    event_name: str | None = None, event_id: str | None = None, count_only: bool | None = None
):
    """Get registrations for an event, optionally returning only the count."""
    return await run_tool_async("get_event_registrations", locals())


async def search_projects(
    title: str | None = None,
    team_name: str | None = None,
    organization: str | None = None,
    industry: str | None = None,
    semester: str | None = None,
    class_code: str | None = None,
):
    """Search student projects by project, team, organization, industry, semester, or class code."""
    return await run_tool_async("search_projects", locals())


async def search_email_campaigns(name: str | None = None, subject: str | None = None, status: str | None = None):
    """Search email campaigns by name, subject, or status."""
    return await run_tool_async("search_email_campaigns", locals())


async def get_campaign_stats(campaign_name: str | None = None, campaign_id: str | None = None):
    """Get detailed delivery statistics for a specific email campaign."""
    return await run_tool_async("get_campaign_stats", locals())


async def search_cms_pages(title: str | None = None, slug: str | None = None, status: str | None = None):
    """Search CMS pages by title, slug, or status."""
    return await run_tool_async("search_cms_pages", locals())


async def search_news(
    title: str | None = None, source: str | None = None, date_from: str | None = None, date_to: str | None = None
):
    """Search news articles by title, source, or date range."""
    return await run_tool_async("search_news", locals())


async def get_page_views(
    path: str | None = None, date_from: str | None = None, date_to: str | None = None, count_only: bool | None = None
):
    """Get page view analytics, optionally filtered by path or date range."""
    return await run_tool_async("get_page_views", locals())


async def get_checkin_stats(event_name: str | None = None, event_id: str | None = None):
    """Get event check-in statistics, optionally filtered by event."""
    return await run_tool_async("get_checkin_stats", locals())


async def search_semesters(year: int | None = None, season: str | None = None, is_published: bool | None = None):
    """Search academic semesters by year, season, or published status."""
    return await run_tool_async("search_semesters", locals())


async def run_custom_query(
    model: str,
    filters: dict[str, Any] | None = None,
    ordering: str | list[str] | None = None,
    fields: list[str] | None = None,
    count_only: bool | None = None,
    limit: int | None = None,
):
    """Run a flexible query against an allowed model using allowlisted fields and filters."""
    return await run_tool_async("run_custom_query", locals())
