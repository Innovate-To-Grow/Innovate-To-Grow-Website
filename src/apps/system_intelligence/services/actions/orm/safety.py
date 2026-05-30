"""Backwards-compatible shim. Logic now lives in core's shared safe-ORM layer.

See ``apps.core.services.db_tools.safe_orm.safety`` — the single source of truth
for the model-access denylist and write-payload validation.
"""

from apps.core.services.db_tools.safe_orm.safety import (
    assign_model_fields,
    coerce_field_value,
    field_output_name,
    field_schema,
    is_field_denied,
    is_model_denied,
    resolve_model,
    safe_model_fields,
    validate_query_key,
    validate_selected_fields,
    validate_write_payload,
)

__all__ = [
    "assign_model_fields",
    "coerce_field_value",
    "field_output_name",
    "field_schema",
    "is_field_denied",
    "is_model_denied",
    "resolve_model",
    "safe_model_fields",
    "validate_query_key",
    "validate_selected_fields",
    "validate_write_payload",
]
