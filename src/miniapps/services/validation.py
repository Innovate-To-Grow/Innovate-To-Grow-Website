import re
from datetime import date, datetime

from rest_framework.exceptions import ValidationError

from miniapps.models.data_schema import FIELD_TYPES


def validate_record_data(schema, data: dict) -> dict:
    """Validate a data dict against a MiniAppDataSchema's field definitions.

    Returns cleaned/coerced data or raises ValidationError.
    """
    if not schema or not schema.fields:
        return data

    field_defs = schema.fields
    field_names = {f["name"] for f in field_defs}
    cleaned = {}
    errors = {}

    for field_def in field_defs:
        name = field_def["name"]
        field_type = field_def.get("type", "text")
        required = field_def.get("required", False)
        value = data.get(name)

        if value is None or value == "":
            if required:
                errors[name] = "This field is required."
            elif "default" in field_def:
                cleaned[name] = field_def["default"]
            continue

        try:
            cleaned[name] = _coerce_value(value, field_type, field_def)
        except (ValueError, TypeError) as e:
            errors[name] = str(e)

    if errors:
        raise ValidationError(errors)

    for key, value in data.items():
        if key not in field_names:
            cleaned[key] = value

    return cleaned


def _coerce_value(value, field_type: str, field_def: dict):
    """Coerce and validate a single value based on its field type."""
    if field_type not in FIELD_TYPES:
        raise ValueError(f"Unknown field type: {field_type}")

    if field_type == "text":
        value = str(value)
        max_length = field_def.get("max_length")
        if max_length and len(value) > max_length:
            raise ValueError(f"Maximum length is {max_length} characters.")
        return value

    if field_type == "integer":
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValueError("Must be an integer.")

    if field_type == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            raise ValueError("Must be a number.")

    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True
            if value.lower() in ("false", "0", "no"):
                return False
        raise ValueError("Must be a boolean.")

    if field_type == "date":
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
                return value
            except ValueError:
                pass
        raise ValueError("Must be a valid ISO date (YYYY-MM-DD).")

    if field_type == "datetime":
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
                return value
            except ValueError:
                pass
        raise ValueError("Must be a valid ISO datetime.")

    if field_type == "email":
        value = str(value)
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", value):
            raise ValueError("Must be a valid email address.")
        return value

    if field_type == "url":
        value = str(value)
        if not value.startswith(("http://", "https://")):
            raise ValueError("Must be a valid URL starting with http:// or https://.")
        return value

    if field_type == "json":
        return value

    return value
