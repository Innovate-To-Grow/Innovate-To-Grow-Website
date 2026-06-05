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


def field_schema_verbose(field: models.Field, *, write: bool) -> dict[str, Any]:
    """Return the shared field schema enriched with CLI-facing metadata.

    ``write`` is accepted for symmetry with the rest of the safe-ORM API (the
    schema endpoint enriches readable and writable fields separately); the extra
    keys are identical either way, but keeping the keyword makes the call sites
    explicit and leaves room for write-only annotations later.
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
        schema["choices"] = [{"value": value, "label": str(label)} for value, label in raw_choices]

    if getattr(field, "is_relation", False) and getattr(field, "related_model", None) is not None:
        related = field.related_model
        schema["related_model"] = related._meta.label
        target = getattr(field, "target_field", None)
        if target is not None:
            schema["related_pk"] = target.name

    return schema
