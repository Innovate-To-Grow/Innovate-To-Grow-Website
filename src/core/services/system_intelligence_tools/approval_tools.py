from typing import Any

from core.services import system_intelligence_actions as action_services

from .runtime import run_action_service_async


async def list_database_models() -> dict[str, Any]:
    """List Django ORM models available for safe reads and proposed single-record writes."""
    return await run_action_service_async(action_services.list_database_models)


async def get_model_schema(app_label: str, model_name: str) -> dict[str, Any]:
    """Get readable and writable fields for a safe Django ORM model."""
    return await run_action_service_async(action_services.get_model_schema, app_label, model_name)


async def get_record(app_label: str, model_name: str, pk: str) -> dict[str, Any]:
    """Get a safe snapshot for one Django ORM record by primary key."""
    return await run_action_service_async(action_services.get_record, app_label, model_name, pk)


async def search_records(
    app_label: str,
    model_name: str,
    filters: dict[str, Any] | None = None,
    ordering: str | list[str] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run a safe, bounded ORM query against readable fields on a Django model."""
    return await run_action_service_async(
        action_services.search_records, app_label, model_name, filters, ordering, fields, limit
    )


async def get_cms_page_detail(
    page_id: str | None = None, slug: str | None = None, route: str | None = None
) -> dict[str, Any]:
    """Get CMS page fields and blocks by page ID, slug, or route."""
    return await run_action_service_async(action_services.get_cms_page_detail, page_id, slug, route)


async def propose_cms_page_update(
    page_id: str | None = None,
    slug: str | None = None,
    route: str | None = None,
    page_fields: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Propose a CMS page change with a cached preview; does not apply without human approval."""
    return await run_action_service_async(
        action_services.propose_cms_page_update, page_id, slug, route, page_fields, blocks, summary
    )


async def propose_db_create(app_label: str, model_name: str, fields: dict[str, Any], summary: str | None = None):
    """Propose creating one database record; does not apply without human approval."""
    return await run_action_service_async(action_services.propose_db_create, app_label, model_name, fields, summary)


async def propose_db_update(
    app_label: str,
    model_name: str,
    pk: str,
    changes: dict[str, Any],
    summary: str | None = None,
) -> dict[str, Any]:
    """Propose updating one database record by primary key; does not apply without human approval."""
    return await run_action_service_async(
        action_services.propose_db_update, app_label, model_name, pk, changes, summary
    )


async def propose_db_delete(app_label: str, model_name: str, pk: str, summary: str | None = None):
    """Propose deleting one database record by primary key; does not apply without human approval."""
    return await run_action_service_async(action_services.propose_db_delete, app_label, model_name, pk, summary)
