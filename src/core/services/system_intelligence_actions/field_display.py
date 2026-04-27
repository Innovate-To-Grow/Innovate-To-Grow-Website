"""Human-readable display helpers for db_* action comparison cards.

Snapshot values stored on `SystemIntelligenceActionRequest` are raw json_safe
values (ISO datetimes, FK ids, raw choice values, booleans). This module
resolves them to display strings at propose-time so the chat card shows
"Yes" instead of `true`, the FK __str__ instead of an integer id, and so on.

Display strings are stored in `payload["comparison"]`; raw snapshots stay
unchanged so `assert_snapshot_unchanged` continues to work.
"""

import json
from datetime import date, datetime
from typing import Any

from django.core.exceptions import FieldDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import formats
from django.utils.dateparse import parse_date, parse_datetime

from .comparison_text import limit_comparison_text
from .orm_records import record_repr

EM_DASH = "—"
DEFAULT_TRUNCATE = 80


def field_label(model: type[models.Model], name: str) -> str:
    """Humanized verbose name for ``name`` on ``model``; falls back to a title-cased identifier."""
    field = _get_field(model, name)
    if field is None:
        return name.replace("_", " ").strip().title() or name
    verbose = getattr(field, "verbose_name", None) or field.name
    return str(verbose).title()


def field_type_name(model: type[models.Model], name: str) -> str:
    """Django field class name for ``name``; ``"Field"`` if unknown."""
    field = _get_field(model, name)
    if field is None:
        return "Field"
    return field.__class__.__name__


def display_value(model: type[models.Model], name: str, raw: Any) -> str:
    """Render a snapshot value for human display.

    Dispatches by Django field class so booleans render as Yes/No, choices
    use their human label, FKs show the related ``__str__``, datetimes get a
    locale-aware short format, JSON gets compacted, and long strings are
    truncated.
    """
    if raw is None:
        return EM_DASH
    field = _get_field(model, name)
    if field is None:
        return _truncate(_stringify(raw))

    if isinstance(field, models.BooleanField):
        if raw is True:
            return "Yes"
        if raw is False:
            return "No"
        return EM_DASH

    flatchoices = getattr(field, "flatchoices", None)
    if flatchoices:
        return str(dict(flatchoices).get(raw, raw))

    if getattr(field, "many_to_one", False):
        return _resolve_fk_display(field, raw)

    if isinstance(field, models.DateTimeField):
        return _format_datetime(raw)
    if isinstance(field, models.DateField):
        return _format_date(raw)

    if isinstance(field, models.JSONField):
        return _format_json(raw)

    if isinstance(field, models.TextField) and isinstance(raw, str):
        return limit_comparison_text(raw)

    return _truncate(_stringify(raw))


# ---- internals ----


def _get_field(model: type[models.Model], name: str) -> models.Field | None:
    try:
        return model._meta.get_field(name)
    except FieldDoesNotExist:
        return None


def _resolve_fk_display(field: models.Field, raw: Any) -> str:
    related_model = getattr(field, "related_model", None)
    if related_model is None or raw in (None, ""):
        return EM_DASH if raw in (None, "") else f"#{raw}"
    try:
        related = related_model._default_manager.filter(pk=raw).first()
    except (TypeError, ValueError):
        related = None
    if related is None:
        return f"#{raw}"
    return record_repr(related)


def _format_datetime(raw: Any) -> str:
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str):
        value = parse_datetime(raw)
    else:
        value = None
    if value is None:
        return _truncate(_stringify(raw))
    return formats.date_format(value, "SHORT_DATETIME_FORMAT")


def _format_date(raw: Any) -> str:
    if isinstance(raw, datetime):
        value = raw.date()
    elif isinstance(raw, date):
        value = raw
    elif isinstance(raw, str):
        value = parse_date(raw) or (parse_datetime(raw).date() if parse_datetime(raw) else None)
    else:
        value = None
    if value is None:
        return _truncate(_stringify(raw))
    return formats.date_format(value, "SHORT_DATE_FORMAT")


def _format_json(raw: Any) -> str:
    if isinstance(raw, dict):
        if len(raw) > 6:
            return f"{{{len(raw)} keys}}"
        return _truncate(json.dumps(raw, cls=DjangoJSONEncoder, default=str))
    if isinstance(raw, list):
        return f"[{len(raw)} items]" if len(raw) > 6 else _truncate(json.dumps(raw, cls=DjangoJSONEncoder, default=str))
    return _truncate(_stringify(raw))


def _stringify(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    try:
        return json.dumps(raw, cls=DjangoJSONEncoder, default=str)
    except TypeError:
        return str(raw)


def _truncate(text: str, limit: int = DEFAULT_TRUNCATE) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
