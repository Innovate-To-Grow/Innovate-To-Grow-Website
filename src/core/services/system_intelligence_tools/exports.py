"""ADK tool wrappers that produce downloadable Excel exports.

The agent calls these when an admin asks to "export", "download", "save as
xlsx", etc. Each wrapper is a thin layer over
``system_intelligence_exports.create_export`` plus the existing ``run_action_service_async``
runtime so we get connection management, friendly error formatting, and the
same context (current user / current conversation) the action proposal tools
already use.
"""

from typing import Any

from core.services import system_intelligence_exports as export_service

from .runtime import run_action_service_async


def _success_payload(export) -> dict[str, Any]:
    return {
        "ok": True,
        "export_id": str(export.id),
        "filename": export.filename,
        "title": export.title,
        "row_count": export.row_count,
        "model_label": export.model_label,
        "fields": list(export.field_names or []),
        "download_url": _download_url(export.id),
        "instruction": (
            "Tell the admin the export is ready and embed the download link as a "
            "markdown link, e.g. [Download " + export.filename + "](" + _download_url(export.id) + ")."
        ),
    }


def _download_url(export_id) -> str:
    return f"/admin/core/system-intelligence/exports/{export_id}/download/"


def _create(*args, **kwargs):
    """Sync entry point — invoked through ``run_action_service_async``."""
    export = export_service.create_export(*args, **kwargs)
    return _success_payload(export)


async def export_records_to_excel(
    app_label: str,
    model_name: str,
    filters: dict[str, Any] | None = None,
    ordering: str | list[str] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Generate a downloadable Excel (xlsx) export of records from a safe model.

    Use after confirming with the admin that they want an xlsx download. The
    returned dict includes a ``download_url`` — surface it to the admin as a
    markdown link in your reply so they can click to download.
    """
    return await run_action_service_async(
        _create,
        app_label=app_label,
        model_name=model_name,
        filters=filters,
        ordering=ordering,
        fields=fields,
        limit=limit,
        title=title,
    )


async def export_members_to_excel(
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Export members to an xlsx file the admin can download. Filter via Django ORM lookups (e.g. ``{"is_active": true}``)."""
    return await run_action_service_async(
        _create,
        app_label="authn",
        model_name="Member",
        filters=filters,
        fields=fields,
        limit=limit,
        title="Members export",
    )


async def export_events_to_excel(
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Export events to an xlsx file the admin can download."""
    return await run_action_service_async(
        _create,
        app_label="event",
        model_name="Event",
        filters=filters,
        fields=fields,
        limit=limit,
        title="Events export",
    )


async def export_projects_to_excel(
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Export projects to an xlsx file the admin can download."""
    return await run_action_service_async(
        _create,
        app_label="projects",
        model_name="Project",
        filters=filters,
        fields=fields,
        limit=limit,
        title="Projects export",
    )


async def export_news_to_excel(
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Export news articles to an xlsx file the admin can download."""
    return await run_action_service_async(
        _create,
        app_label="cms",
        model_name="NewsArticle",
        filters=filters,
        fields=fields,
        limit=limit,
        title="News export",
    )
