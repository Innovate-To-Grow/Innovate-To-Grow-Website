"""
Field resolver for generic model-to-sheet column mapping.

Uses Django __ syntax to handle ForeignKey resolution:
    {"Year": "semester__year", "Season": "semester__season"}

The sync engine groups __ fields by FK prefix and resolves them
via get() or get_or_create() based on fk_config.
"""

import logging

from django.db import models

logger = logging.getLogger(__name__)


def group_fk_columns(column_mapping: dict) -> tuple[dict, dict]:
    """
    Scan column_mapping for __ separators.

    Returns:
        (fk_groups, direct_mappings)
        fk_groups: {fk_field: {related_field: sheet_header}}
            e.g. {"semester": {"year": "Year", "season": "Season"}}
        direct_mappings: {sheet_header: model_field}
            e.g. {"Class": "class_code", "Team#": "team_number"}
    """
    fk_groups: dict[str, dict[str, str]] = {}
    direct_mappings: dict[str, str] = {}

    for sheet_header, field_path in column_mapping.items():
        if field_path == "__skip__":
            continue
        if "__" in field_path:
            fk_field, related_field = field_path.split("__", 1)
            fk_groups.setdefault(fk_field, {})[related_field] = sheet_header
        else:
            direct_mappings[sheet_header] = field_path

    return fk_groups, direct_mappings


def coerce_field_value(field: models.Field, raw_value: str):
    """
    Coerce a raw string value to the correct Python type based on the Django field.

    Returns the coerced value, or the raw string if coercion is not needed.
    """
    if raw_value == "" and field.null:
        return None
    if raw_value == "" and hasattr(field, "default") and field.default is not models.NOT_PROVIDED:
        return field.default if not callable(field.default) else field.default()

    if isinstance(field, models.IntegerField | models.SmallIntegerField | models.BigIntegerField):
        return int(raw_value)
    if isinstance(field, models.PositiveIntegerField):
        return int(raw_value)
    if isinstance(field, models.FloatField | models.DecimalField):
        return float(raw_value)
    if isinstance(field, models.BooleanField):
        return raw_value.lower() in ("true", "1", "yes")
    if isinstance(field, models.NullBooleanField):
        if raw_value.lower() in ("true", "1", "yes"):
            return True
        if raw_value.lower() in ("false", "0", "no"):
            return False
        return None

    # CharField, TextField, etc. — return as-is
    return raw_value


def resolve_fk(model_class, fk_field_name: str, lookup_dict: dict, fk_config: dict):
    """
    Resolve a ForeignKey value from grouped column values.

    Args:
        model_class: The parent model class (e.g., Project)
        fk_field_name: The FK field name on the parent (e.g., "semester")
        lookup_dict: Raw string values for the related model fields
            e.g. {"year": "2025", "season": "2"}
        fk_config: FK config from SheetLink.fk_config for this FK field
            e.g. {"create_if_missing": True, "defaults": {"is_published": True}}

    Returns:
        The resolved related model instance.

    Raises:
        ValueError: If the FK target cannot be resolved.
    """
    fk_django_field = model_class._meta.get_field(fk_field_name)
    related_model = fk_django_field.related_model

    # Coerce raw string values to proper types based on the related model's fields
    coerced_lookup = {}
    for related_field_name, raw_value in lookup_dict.items():
        try:
            related_field = related_model._meta.get_field(related_field_name)
            coerced_lookup[related_field_name] = coerce_field_value(related_field, raw_value)
        except Exception:  # noqa: BLE001
            coerced_lookup[related_field_name] = raw_value

    config = fk_config.get(fk_field_name, {})
    create_if_missing = config.get("create_if_missing", False)
    defaults = config.get("defaults", {})

    if create_if_missing:
        instance, _created = related_model.objects.get_or_create(**coerced_lookup, defaults=defaults)
        return instance

    try:
        return related_model.objects.get(**coerced_lookup)
    except related_model.DoesNotExist:
        raise ValueError(
            f"{related_model.__name__} not found with {coerced_lookup}. "
            f'Set create_if_missing=true in fk_config["{fk_field_name}"] to auto-create.'
        )
    except related_model.MultipleObjectsReturned:
        raise ValueError(
            f"Multiple {related_model.__name__} found with {coerced_lookup}. Ensure lookup fields are unique."
        )


def serialize_field_value(obj, field_path: str) -> str:
    """
    Read a field value from a model instance and return it as a string for a sheet cell.

    Supports both direct fields ("class_code") and __ FK fields ("semester__year").
    """
    if "__" in field_path:
        fk_field, related_field = field_path.split("__", 1)
        related_obj = getattr(obj, fk_field, None)
        if related_obj is None:
            return ""
        value = getattr(related_obj, related_field, "")
    else:
        value = getattr(obj, field_path, "")

    if value is None:
        return ""
    return str(value)
