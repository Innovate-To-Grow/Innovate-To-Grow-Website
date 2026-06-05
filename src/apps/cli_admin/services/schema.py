"""CLI-local schema enrichment.

The shared, security-critical primitive
``apps.core.services.db_tools.safe_orm.field_schema`` returns the minimal field
shape ``{name, type, required, choices}`` and is also consumed by
``system_intelligence``. To keep that AI-facing surface unchanged, the CLI adds
its richer metadata here instead of touching the shared helper.

``field_schema_verbose`` starts from the shared ``field_schema`` output and layers
on human-facing labels (``verbose_name``, ``help_text``), constraint flags
(``blank``, ``null``), a concrete ``default`` (callable/unset defaults are
skipped), structured ``choices`` (``[{value, label}]``), and relational target
info (``related_model`` + ``related_pk``). Everything is read defensively so an
exotic field never raises.
"""

from typing import Any

from django.db import models
from django.db.models import NOT_PROVIDED

from apps.core.services.db_tools.safe_orm import field_schema


def _flatten_choices(raw_choices: Any) -> list[dict[str, Any]]:
    """Defensively flatten Django ``choices`` into ``[{value, label}]``.

    Django normalizes grouped (optgroup) choices to ``[("Group", [(v, l), ...])]``
    while flat choices stay ``[(v, l), ...]``. Entries whose second element is a
    list/tuple are treated as a group and their inner ``(v, l)`` pairs expanded;
    everything else is read as a flat ``(value, label)`` pair. Any malformed entry
    is skipped so this never raises (the caller relies on "never raises").
    """
    flattened: list[dict[str, Any]] = []
    for entry in raw_choices:
        try:
            value, label = entry
        except (TypeError, ValueError):
            continue
        if isinstance(label, list | tuple):
            for inner in label:
                try:
                    inner_value, inner_label = inner
                except (TypeError, ValueError):
                    continue
                flattened.append({"value": inner_value, "label": str(inner_label)})
        else:
            flattened.append({"value": value, "label": str(label)})
    return flattened


def field_schema_verbose(field: models.Field) -> dict[str, Any]:
    """Return the shared field schema enriched with CLI-facing metadata.

    Layers human-facing labels (``verbose_name``, ``help_text``), constraint flags
    (``blank``, ``null``), a concrete ``default`` (callable/unset defaults are
    skipped), structured ``choices`` (``[{value, label}]``, optgroups flattened),
    and relational target info (``related_model`` + ``related_pk``). Everything is
    read defensively so an exotic field never raises.
    """
    schema = dict(field_schema(field))

    verbose_name = getattr(field, "verbose_name", None)
    if verbose_name is not None:
        schema["verbose_name"] = str(verbose_name)

    help_text = getattr(field, "help_text", None)
    if help_text:
        schema["help_text"] = str(help_text)

    schema["blank"] = bool(getattr(field, "blank", False))
    schema["null"] = bool(getattr(field, "null", False))

    default = getattr(field, "default", NOT_PROVIDED)
    if default is not NOT_PROVIDED and not callable(default):
        schema["default"] = default

    raw_choices = getattr(field, "choices", None)
    if raw_choices:
        try:
            choices = _flatten_choices(raw_choices)
        except Exception:
            choices = []
        if choices:
            schema["choices"] = choices

    if getattr(field, "is_relation", False) and getattr(field, "related_model", None) is not None:
        related = field.related_model
        schema["related_model"] = related._meta.label
        target = getattr(field, "target_field", None)
        if target is not None:
            schema["related_pk"] = target.name

    return schema
