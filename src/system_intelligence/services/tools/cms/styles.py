from typing import Any

from system_intelligence.services.actions.exceptions import ActionRequestError

from ..query_helpers import object_payload, queryset_payload, require_one
from ..runtime import run_action_service_async


async def search_style_sheets(
    name: str | None = None, is_active: bool | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Search admin-managed style sheets by name or active state."""
    return await run_action_service_async(_search_style_sheets, name, is_active, limit)


async def get_style_sheet_detail(sheet_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    """Get one admin-managed style sheet including CSS length and content."""
    return await run_action_service_async(_get_style_sheet_detail, sheet_id, name)


def _search_style_sheets(name=None, is_active=None, limit=None) -> dict[str, Any]:
    from cms.models import StyleSheet

    qs = StyleSheet.objects.all()
    if name:
        qs = qs.filter(name__icontains=name)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return queryset_payload(
        qs.order_by("sort_order", "name"),
        ["id", "name", "display_name", "description", "is_active", "sort_order"],
        limit=limit,
    )


def _get_style_sheet_detail(sheet_id=None, name=None) -> dict[str, Any]:
    from cms.models import StyleSheet

    qs = StyleSheet.objects.all()
    if sheet_id:
        sheet = require_one(qs.filter(pk=sheet_id), "Style sheet")
    elif name:
        sheet = require_one(qs.filter(name__icontains=name), "Style sheet")
    else:
        raise ActionRequestError("Provide sheet_id or name.")
    payload = object_payload(sheet, ["id", "name", "display_name", "description", "css", "is_active", "sort_order"])
    payload["css_length"] = len(sheet.css or "")
    return {"style_sheet": payload}
