from typing import Any

from django.db.models import QuerySet

from core.services.db_tools.helpers import MAX_ROWS
from core.services.system_intelligence_actions.exceptions import ActionRequestError
from core.services.system_intelligence_actions.utils import json_safe


def bounded_limit(limit: int | None = None, *, default: int = 20) -> int:
    try:
        value = int(limit or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, MAX_ROWS))


def queryset_payload(qs: QuerySet, fields: list[str], *, limit: int | None = None) -> dict[str, Any]:
    row_limit = bounded_limit(limit)
    rows = list(qs.values(*fields)[:row_limit])
    return {"shown": len(rows), "total": qs.count(), "rows": json_safe(rows)}


def object_payload(obj, fields: list[str]) -> dict[str, Any]:
    data = {}
    for field in fields:
        data[field] = getattr(obj, field)
    data["__repr__"] = str(obj)
    return json_safe(data)


def require_one(qs: QuerySet, label: str):
    obj = qs.first()
    if obj is None:
        raise ActionRequestError(f"{label} was not found.")
    return obj


def apply_date_range(qs: QuerySet, field: str, date_from: str | None = None, date_to: str | None = None) -> QuerySet:
    if date_from:
        qs = qs.filter(**{f"{field}__gte": date_from})
    if date_to:
        qs = qs.filter(**{f"{field}__lte": date_to})
    return qs
