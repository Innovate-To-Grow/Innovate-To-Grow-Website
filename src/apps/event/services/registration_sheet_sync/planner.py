"""Pure reconciliation planning: labels bootstrap identity; metadata keeps it stable."""

import hashlib
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from .provider import METADATA_PREFIX


def normalized_label(value):
    return " ".join(unicodedata.normalize("NFC", str(value)).split()).casefold()


@dataclass
class SyncPlan:
    bindings: dict = field(default_factory=dict)
    new_bindings: dict = field(default_factory=dict)
    cells: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    legacy_matches: list = field(default_factory=list)
    active_ids: list = field(default_factory=list)
    deleted_ids: list = field(default_factory=list)
    label_changes: list = field(default_factory=list)
    requires_adoption: bool = False
    counts: dict = field(
        default_factory=lambda: {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0, "header_changes": 0}
    )
    fingerprint: str = ""


def _cell(snapshot, row, column):
    return (
        str(snapshot.values[row - 1][column - 1])
        if row <= len(snapshot.values) and column <= len(snapshot.values[row - 1])
        else ""
    )


def _bind_columns(plan, snapshot, fields, event_id, config):
    header_row = config.header_row
    header = snapshot.values[header_row - 1] if header_row <= len(snapshot.values) else []
    own_key = f"{METADATA_PREFIX}{event_id}"
    header_markers = []
    configured_labels = {}
    managed = False
    for metadata in snapshot.metadata:
        dimension = metadata.get("location", {}).get("dimensionRange", {})
        location = metadata.get("location", {})
        if dimension.get("sheetId", location.get("sheetId")) != snapshot.sheet_id:
            continue
        metadata_key = metadata.get("metadataKey", "")
        if metadata_key == f"i2g.registration-label.v1:{event_id}":
            managed = True
            try:
                label_setting = json.loads(metadata.get("metadataValue", ""))
                label_key = label_setting["key"]
                if label_key in configured_labels:
                    raise ValueError("duplicate label metadata")
                configured_labels[label_key] = {**label_setting, "metadata_id": metadata["metadataId"]}
            except (ValueError, KeyError, TypeError):
                plan.conflicts.append("Invalid or duplicate configured-label metadata.")
            continue
        if metadata_key.startswith("i2g.registration-label.v1:"):
            plan.conflicts.append("This worksheet is managed by a different event. Choose a separate worksheet.")
            continue
        if not metadata_key.startswith(METADATA_PREFIX):
            continue
        if metadata_key != own_key:
            plan.conflicts.append("This worksheet is managed by a different event. Choose a separate worksheet.")
            continue
        managed = True
        key = metadata.get("metadataValue", "")
        if key == "__header__":
            header_markers.append(dimension)
            continue
        if dimension.get("dimension") != "COLUMNS":
            plan.conflicts.append(f"Invalid managed column location: {key}.")
            continue
        column = dimension.get("startIndex", 0) + 1
        if not key or dimension.get("endIndex") != column or key in plan.bindings or column in plan.bindings.values():
            plan.conflicts.append(f"Duplicate or invalid managed column binding: {key or 'unknown field'}.")
            continue
        plan.bindings[key] = column
    if managed and not header_markers:
        plan.conflicts.append(
            "Managed header row metadata is missing. Restore the header row or create a new worksheet."
        )
    if managed and "registration_id" not in plan.bindings:
        plan.conflicts.append(
            "Managed Registration ID column metadata is missing. Restore the ID column or create a new worksheet."
        )
    if len(header_markers) > 1 or any(
        item.get("dimension") != "ROWS"
        or item.get("startIndex") != header_row - 1
        or item.get("endIndex") != header_row
        for item in header_markers
    ):
        plan.conflicts.append(
            "Managed header row does not match the configured header row. Correct the setting before syncing."
        )

    candidates = {}
    explicit = config.column_mappings or {}
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
        if definition.key in explicit:
            column = explicit[definition.key]
            if not isinstance(column, int) or isinstance(column, bool) or column < 1 or column > snapshot.column_count:
                plan.conflicts.append(f"Invalid explicit column mapping for {definition.label}.")
                continue
            matches = [column]
        else:
            labels = {normalized_label(label) for label in (definition.label, *definition.aliases)}
            matches = [index + 1 for index, label in enumerate(header) if normalized_label(label) in labels]
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

    # For populated sheets append beyond the existing grid, including blank custom columns.
    next_column = max([snapshot.column_count if snapshot.values else 0, *plan.bindings.values()], default=0) + 1
    for definition in fields:
        if not definition.enabled:
            continue
        key = definition.key
        if key not in plan.bindings:
            plan.bindings[key] = next_column
            plan.new_bindings[key] = next_column
            next_column += 1
        column = plan.bindings[key]
        if column > 18278:
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


def _legacy_match(row_values, current_values):
    code = row_values.get("ticket_code", "").strip()
    if code:
        return [key for key, values in current_values.items() if values["ticket_code"] == code]
    identity = ("created_at", "primary_email", "ticket_type", "first_name", "last_name")
    if not all(row_values.get(key, "").strip() for key in identity):
        return []
    return [
        key
        for key, values in current_values.items()
        if all(row_values[key].strip() == values[key].strip() for key in identity)
    ]


def plan_sync(snapshot, *, fields, current_values, deleted_ids, known_ids, event_id, config):
    plan = SyncPlan()
    _bind_columns(plan, snapshot, fields, event_id, config)
    enabled = [definition.key for definition in fields if definition.enabled]
    id_column = plan.bindings["registration_id"]
    existing_id_binding = (
        "registration_id" not in plan.new_bindings
        or "registration_id" in (config.column_mappings or {})
        or any(
            normalized_label(label) == "registration id"
            for label in (snapshot.values[config.header_row - 1] if len(snapshot.values) >= config.header_row else [])
        )
    )
    id_rows = {}
    legacy = []
    for row in range(config.header_row + 1, len(snapshot.values) + 1):
        registration_id = _cell(snapshot, row, id_column).strip()
        if registration_id:
            if registration_id in id_rows:
                plan.conflicts.append(f"Registration ID {registration_id} appears in multiple rows.")
            elif registration_id not in current_values and registration_id not in known_ids:
                if registration_id in deleted_ids:
                    plan.conflicts.append(
                        f"Row {row} belongs to a deleted registration without a completed sync receipt. Review the interrupted sync and create a new worksheet."
                    )
                else:
                    plan.conflicts.append(f"Row {row} has an unknown Registration ID: {registration_id}.")
            id_rows[registration_id] = row
            continue
        row_values = {key: _cell(snapshot, row, column) for key, column in plan.bindings.items() if key in enabled}
        # Completely custom rows remain untouched, including their formulas.
        if not any(value.strip() for value in row_values.values()):
            if any(str(value).strip() for value in snapshot.values[row - 1]) and not existing_id_binding:
                plan.conflicts.append(
                    f"Row {row} contains data without a recognized registration identity. Choose explicit mappings or a new worksheet."
                )
            continue
        matches = _legacy_match(row_values, current_values)
        if len(matches) != 1:
            plan.conflicts.append(
                f"Row {row} has no unique registration identity. Match by Ticket Code or choose a new worksheet."
            )
            continue
        legacy.append((row, matches[0]))
    legacy_counts = Counter(registration_id for _, registration_id in legacy)
    for row, registration_id in legacy:
        if legacy_counts[registration_id] != 1 or registration_id in id_rows:
            plan.conflicts.append(f"Row {row} matches a registration already present in another row.")
            continue
        id_rows[registration_id] = row
        plan.legacy_matches.append(
            {
                "row": row,
                "registration_id": registration_id,
                "ticket_code": current_values[registration_id]["ticket_code"],
            }
        )
    plan.requires_adoption = bool(plan.legacy_matches)
    next_row = max(config.header_row, len(snapshot.values)) + 1
    for registration_id, values in current_values.items():
        row = id_rows.get(registration_id)
        new = row is None
        if new:
            row = next_row
            next_row += 1
        changed = False
        for key in enabled:
            desired = values.get(key, "")
            column = plan.bindings[key]
            if _cell(snapshot, row, column) != desired:
                plan.cells[(row, column)] = desired
                changed = True
        plan.counts["added" if new else "updated" if changed else "unchanged"] += 1
        plan.active_ids.append(registration_id)
    for registration_id in deleted_ids:
        if registration_id not in id_rows or registration_id not in known_ids:
            continue
        row = id_rows[registration_id]
        column = plan.bindings["status"]
        if _cell(snapshot, row, column) != "Deleted":
            plan.cells[(row, column)] = "Deleted"
            plan.counts["deleted"] += 1
        plan.deleted_ids.append(registration_id)
    plan.fingerprint = hashlib.sha256(
        json.dumps(
            {
                "sheet": snapshot.fingerprint(),
                "fields": [definition.__dict__ for definition in fields],
                "header_row": config.header_row,
                "mappings": config.column_mappings,
                "source": current_values,
                "deleted_ids": sorted(deleted_ids),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return plan
