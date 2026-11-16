"""How a field value is shown in a confirmation diff."""

import uuid
from datetime import date, datetime

from django.db import models
from django.utils.timezone import is_aware


def summarize_large_value(value):
    """Format a value, replacing a long blob with a size summary instead of a truncated prefix.

    A 200-char slice of a base64 ``data:`` URI is noise that crowds out the fields an admin actually
    needs to read on a delete-confirmation page.
    """
    if isinstance(value, str) and len(value) > 200:
        if value.startswith("data:"):
            kind = value[5 : value.find(";")] or "binary"
            return f"<{kind} data, {len(value) // 1024} KB>"
        return f"<{len(value)} characters>"
    return format_field_value(value)


def _format_structured(value) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:200]
    except (TypeError, ValueError):
        return str(value)[:200]


def _format_datetime(value: datetime) -> str:
    fmt = "%Y-%m-%d %H:%M:%S"
    if is_aware(value):
        fmt += " %Z"
    return value.strftime(fmt)


def format_field_value(value):
    """Format a field value for human-readable display."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return _format_datetime(value)
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, uuid.UUID | models.Model):
        return str(value)
    if isinstance(value, list | dict):
        return _format_structured(value)
    if isinstance(value, models.QuerySet):
        return ", ".join(str(v) for v in value[:10])
    value_str = str(value)
    if len(value_str) > 200:
        return value_str[:200] + "..."
    return value_str
