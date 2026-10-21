"""Build empty CLI input skeletons from a model schema.

``build_skeleton`` turns the ``writable_fields`` of a model schema (as returned by
``GET /admin-api/models/{app}/{model}/schema/``) into an empty JSON template the
caller can fill in and feed back through ``--cli-input-json``. This mirrors AWS
CLI's ``--generate-cli-skeleton``.
"""

from typing import Any

# Field class names (the schema ``type``) grouped by the empty placeholder they
# should map to. Anything not listed falls through to ``None`` (JSON ``null``),
# which is a safe, explicit "fill me in" marker.
_STRING_FIELDS = frozenset(
    {
        "CharField",
        "TextField",
        "SlugField",
        "EmailField",
        "URLField",
        "GenericIPAddressField",
        "UUIDField",
        "DateField",
        "DateTimeField",
        "TimeField",
        "DurationField",
        "FilePathField",
    }
)
_INT_FIELDS = frozenset(
    {
        "IntegerField",
        "BigIntegerField",
        "SmallIntegerField",
        "PositiveIntegerField",
        "PositiveSmallIntegerField",
        "PositiveBigIntegerField",
        "ForeignKey",
        "OneToOneField",
    }
)
_FLOAT_FIELDS = frozenset({"FloatField", "DecimalField"})
_BOOL_FIELDS = frozenset({"BooleanField", "NullBooleanField"})
_LIST_FIELDS = frozenset({"ManyToManyField", "ArrayField"})
_DICT_FIELDS = frozenset({"JSONField"})


def _placeholder(field: dict[str, Any]) -> Any:
    """Return a type-appropriate empty placeholder for one writable field."""
    field_type = field.get("type")
    if field_type in _STRING_FIELDS:
        return ""
    if field_type in _INT_FIELDS:
        return 0
    if field_type in _FLOAT_FIELDS:
        return 0.0
    if field_type in _BOOL_FIELDS:
        return False
    if field_type in _LIST_FIELDS:
        return []
    if field_type in _DICT_FIELDS:
        return {}
    return None


def build_skeleton(schema: dict[str, Any]) -> dict[str, Any]:
    """Build an empty input template from a model schema.

    One key per ``writable_fields`` entry, mapped to a deterministic empty
    placeholder by field type. Fields the CLI does not recognize map to ``None``.
    """
    skeleton: dict[str, Any] = {}
    for field in schema.get("writable_fields") or []:
        name = field.get("name")
        if name is None:
            continue
        skeleton[name] = _placeholder(field)
    return skeleton
