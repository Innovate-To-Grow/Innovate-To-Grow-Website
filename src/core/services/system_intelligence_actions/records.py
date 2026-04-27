import json
from typing import Any

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder

from core.services.db_tools.helpers import MAX_ROWS, _truncate

from .exceptions import ActionRequestError
from .orm import (
    field_output_name,
    field_schema,
    get_object,
    is_model_denied,
    resolve_model,
    safe_model_fields,
    serialize_model_instance,
    validate_query_key,
    validate_selected_fields,
)
from .utils import json_safe


def list_database_models() -> str:
    """List ORM models available for safe System Intelligence reads/writes."""
    rows = []
    for model in apps.get_models():
        if is_model_denied(model, write=False):
            continue
        rows.append(
            {
                "app_label": model._meta.app_label,
                "model_name": model._meta.object_name,
                "label": model._meta.label,
                "writable": not is_model_denied(model, write=True),
            }
        )
    rows.sort(key=lambda item: item["label"])
    return _truncate(json.dumps(rows, indent=2, cls=DjangoJSONEncoder))


def get_model_schema(app_label: str, model_name: str) -> str:
    """Return readable/writable fields for a safe ORM model."""
    model = resolve_model(app_label, model_name, write=False)
    return _truncate(
        json.dumps(
            {
                "model": model._meta.label,
                "primary_key": model._meta.pk.name,
                "readable_fields": [field_schema(field) for field in safe_model_fields(model, write=False)],
                "writable_fields": [field_schema(field) for field in safe_model_fields(model, write=True)],
                "write_rules": "Create/update/delete require a pending action request and human approval.",
            },
            indent=2,
            cls=DjangoJSONEncoder,
        )
    )


def get_record(app_label: str, model_name: str, pk: str) -> str:
    """Return a safe snapshot for one ORM record."""
    model = resolve_model(app_label, model_name, write=False)
    payload = serialize_model_instance(get_object(model, pk), write=False)
    return _truncate(json.dumps(payload, indent=2, cls=DjangoJSONEncoder))


def search_records(
    app_label: str,
    model_name: str,
    filters: dict[str, Any] | None = None,
    ordering: str | list[str] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
) -> str:
    """Run a safe, bounded ORM query against readable fields."""
    model = resolve_model(app_label, model_name, write=False)
    safe_names = {field_output_name(field) for field in safe_model_fields(model, write=False)}
    selected_fields = validate_selected_fields(fields, safe_names) if fields else sorted(safe_names)
    qs = model.objects.all()
    filters = filters or {}
    if not isinstance(filters, dict):
        raise ActionRequestError("filters must be an object.")
    for key in filters:
        validate_query_key(key, safe_names)
    if filters:
        qs = qs.filter(**filters)
    if ordering:
        ordering_list = [ordering] if isinstance(ordering, str) else list(ordering)
        for key in ordering_list:
            validate_query_key(key, safe_names)
        qs = qs.order_by(*ordering_list)
    rows = [json_safe(row) for row in qs.values(*selected_fields)[: min(int(limit or MAX_ROWS), MAX_ROWS)]]
    payload = {"model": model._meta.label, "shown": len(rows), "total": qs.count(), "rows": rows}
    return _truncate(json.dumps(payload, indent=2, cls=DjangoJSONEncoder))
