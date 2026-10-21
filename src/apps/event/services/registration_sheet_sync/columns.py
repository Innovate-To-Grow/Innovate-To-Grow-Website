"""Binding plan columns to worksheet columns: metadata ownership, label bootstrapping, managed structure."""

import json
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from .provider import METADATA_PREFIX


def normalized_label(value):
    return " ".join(unicodedata.normalize("NFC", str(value)).split()).casefold()


def _cell(snapshot, row, column):
    return (
        str(snapshot.values[row - 1][column - 1])
        if row <= len(snapshot.values) and column <= len(snapshot.values[row - 1])
        else ""
    )


_FOREIGN_WORKSHEET = "This worksheet is managed by a different event. Choose a separate worksheet."
_MAX_COLUMN = 18278  # Column "ZZZ", the last one the A1 notation used here can address.


@dataclass
class _WorksheetMetadata:
    """What the worksheet's developer metadata says this event already owns."""

    managed: bool = False
    header_markers: list = field(default_factory=list)
    configured_labels: dict = field(default_factory=dict)


def _read_label_setting(plan, metadata, owned):
    owned.managed = True
    try:
        label_setting = json.loads(metadata.get("metadataValue", ""))
        label_key = label_setting["key"]
        if label_key in owned.configured_labels:
            raise ValueError("duplicate label metadata")
        owned.configured_labels[label_key] = {**label_setting, "metadata_id": metadata["metadataId"]}
    except (ValueError, KeyError, TypeError):
        plan.conflicts.append("Invalid or duplicate configured-label metadata.")


def _read_column_binding(plan, metadata, dimension, owned):
    owned.managed = True
    key = metadata.get("metadataValue", "")
    if key == "__header__":
        owned.header_markers.append(dimension)
        return
    if dimension.get("dimension") != "COLUMNS":
        plan.conflicts.append(f"Invalid managed column location: {key}.")
        return
    column = dimension.get("startIndex", 0) + 1
    if not key or dimension.get("endIndex") != column or key in plan.bindings or column in plan.bindings.values():
        plan.conflicts.append(f"Duplicate or invalid managed column binding: {key or 'unknown field'}.")
        return
    plan.bindings[key] = column


def _read_metadata(plan, snapshot, event_id) -> _WorksheetMetadata:
    own_key = f"{METADATA_PREFIX}{event_id}"
    owned = _WorksheetMetadata()
    for metadata in snapshot.metadata:
        dimension = metadata.get("location", {}).get("dimensionRange", {})
        location = metadata.get("location", {})
        if dimension.get("sheetId", location.get("sheetId")) != snapshot.sheet_id:
            continue
        metadata_key = metadata.get("metadataKey", "")
        if metadata_key == f"i2g.registration-label.v1:{event_id}":
            _read_label_setting(plan, metadata, owned)
        elif metadata_key.startswith("i2g.registration-label.v1:"):
            plan.conflicts.append(_FOREIGN_WORKSHEET)
        elif not metadata_key.startswith(METADATA_PREFIX):
            continue
        elif metadata_key != own_key:
            plan.conflicts.append(_FOREIGN_WORKSHEET)
        else:
            _read_column_binding(plan, metadata, dimension, owned)
    return owned


def _check_managed_structure(plan, owned, header_row):
    if owned.managed and not owned.header_markers:
        plan.conflicts.append(
            "Managed header row metadata is missing. Restore the header row or create a new worksheet."
        )
    if owned.managed and "registration_id" not in plan.bindings:
        plan.conflicts.append(
            "Managed Registration ID column metadata is missing. Restore the ID column or create a new worksheet."
        )
    if len(owned.header_markers) > 1 or any(
        item.get("dimension") != "ROWS"
        or item.get("startIndex") != header_row - 1
        or item.get("endIndex") != header_row
        for item in owned.header_markers
    ):
        plan.conflicts.append(
            "Managed header row does not match the configured header row. Correct the setting before syncing."
        )


def _matching_columns(plan, definition, explicit, header, column_count):
    """Columns an unbound field could adopt on first setup: its explicit mapping, else matching labels."""
    if definition.key in explicit:
        column = explicit[definition.key]
        if not isinstance(column, int) or isinstance(column, bool) or column < 1 or column > column_count:
            plan.conflicts.append(f"Invalid explicit column mapping for {definition.label}.")
            return []
        return [column]
    labels = {normalized_label(label) for label in (definition.label, *definition.aliases)}
    return [index + 1 for index, label in enumerate(header) if normalized_label(label) in labels]


def _adopt_existing_columns(plan, snapshot, fields, header, managed, explicit):
    candidates = {}
    for definition in fields:
        if not definition.enabled or definition.key in plan.bindings:
            continue
        if managed:
            if definition.key in explicit:
                plan.conflicts.append(
                    f"Column mappings apply only to initial setup. Clear the mapping for {definition.label} to append a new managed column."
                )
            # Once ownership is established, a matching label may be a custom
            # organizer column. Only initial bootstrap can infer its ownership.
            continue
        matches = _matching_columns(plan, definition, explicit, header, snapshot.column_count)
        if len(matches) > 1:
            plan.conflicts.append(f"Multiple columns match {definition.label}. Set an explicit column mapping.")
        elif matches:
            candidates[definition.key] = matches[0]
    counts = Counter(candidates.values())
    for key, column in candidates.items():
        if counts[column] != 1 or column in plan.bindings.values():
            plan.conflicts.append(f"Column {column} is assigned to more than one managed field.")
            continue
        plan.bindings[key] = column
        plan.new_bindings[key] = column


def _label_column(plan, snapshot, definition, header_row, configured_labels):
    key = definition.key
    column = plan.bindings[key]
    if column > _MAX_COLUMN:
        plan.conflicts.append(
            "This worksheet has no safe space for additional managed columns. Create a new worksheet."
        )
    current_label = _cell(snapshot, header_row, column)
    # Keep human renames on existing bindings unless an explicit label was configured.
    previous_label = configured_labels.get(key, {}).get("label", "")
    configured_label = definition.label if definition.explicit_label else ""
    changed_setting = previous_label != configured_label
    label = definition.label if changed_setting or not current_label else current_label
    if changed_setting:
        plan.label_changes.append(
            {
                "key": key,
                "column": column,
                "label": configured_label,
                "metadata_id": configured_labels.get(key, {}).get("metadata_id"),
            }
        )
    if label != current_label:
        plan.cells[(header_row, column)] = label
        plan.counts["header_changes"] += 1
    plan.columns.append(
        {
            "key": key,
            "label": label,
            "current_label": current_label,
            "column": column,
            "managed": key not in plan.new_bindings,
            "enabled": True,
            "action": "bind" if key in plan.new_bindings else "keep",
        }
    )


def _bind_columns(plan, snapshot, fields, event_id, config):
    header_row = config.header_row
    header = snapshot.values[header_row - 1] if header_row <= len(snapshot.values) else []
    owned = _read_metadata(plan, snapshot, event_id)
    plan.managed = owned.managed
    _check_managed_structure(plan, owned, header_row)
    _adopt_existing_columns(plan, snapshot, fields, header, owned.managed, config.column_mappings or {})

    # For populated sheets append beyond the existing grid, including blank custom columns.
    next_column = max([snapshot.column_count if snapshot.values else 0, *plan.bindings.values()], default=0) + 1
    for definition in fields:
        if not definition.enabled:
            continue
        if definition.key not in plan.bindings:
            plan.bindings[definition.key] = next_column
            plan.new_bindings[definition.key] = next_column
            next_column += 1
        _label_column(plan, snapshot, definition, header_row, owned.configured_labels)
