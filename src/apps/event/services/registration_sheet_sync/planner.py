"""Pure reconciliation planning: labels bootstrap identity; metadata keeps it stable."""

import hashlib
import json
import uuid
from collections import Counter
from dataclasses import dataclass, field

from .columns import _bind_columns, _cell, normalized_label


@dataclass
class SyncPlan:
    bindings: dict = field(default_factory=dict)
    new_bindings: dict = field(default_factory=dict)
    cells: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    legacy_matches: list = field(default_factory=list)
    stale_rows: list = field(default_factory=list)
    active_ids: list = field(default_factory=list)
    deleted_ids: list = field(default_factory=list)
    label_changes: list = field(default_factory=list)
    requires_adoption: bool = False
    managed: bool = False
    counts: dict = field(
        default_factory=lambda: {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0, "header_changes": 0}
    )
    fingerprint: str = ""


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


def _is_canonical_uuid(value):
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _has_existing_id_binding(plan, snapshot, config):
    return (
        "registration_id" not in plan.new_bindings
        or "registration_id" in (config.column_mappings or {})
        or any(
            normalized_label(label) == "registration id"
            for label in (snapshot.values[config.header_row - 1] if len(snapshot.values) >= config.header_row else [])
        )
    )


def _check_identified_row(plan, row, registration_id, id_rows, *, current_values, known_ids, deleted_ids):
    if registration_id in id_rows:
        plan.conflicts.append(f"Registration ID {registration_id} appears in multiple rows.")
    elif registration_id not in current_values and registration_id not in known_ids:
        if not plan.managed and _is_canonical_uuid(registration_id):
            # Append-only exports kept rows for registrations deleted
            # before receipts existed. Adoption marks them deleted.
            plan.stale_rows.append({"row": row, "registration_id": registration_id})
        elif registration_id in deleted_ids:
            plan.conflicts.append(
                f"Row {row} belongs to a deleted registration without a completed sync receipt. Review the interrupted sync and create a new worksheet."
            )
        else:
            plan.conflicts.append(f"Row {row} has an unknown Registration ID: {registration_id}.")


def _match_unidentified_row(plan, snapshot, row, enabled, current_values, existing_id_binding):
    """A row without a Registration ID: the registration it is (legacy export), or None."""
    row_values = {key: _cell(snapshot, row, column) for key, column in plan.bindings.items() if key in enabled}
    # Completely custom rows remain untouched, including their formulas.
    if not any(value.strip() for value in row_values.values()):
        if any(str(value).strip() for value in snapshot.values[row - 1]) and not existing_id_binding:
            plan.conflicts.append(
                f"Row {row} contains data without a recognized registration identity. Choose explicit mappings or a new worksheet."
            )
        return None
    matches = _legacy_match(row_values, current_values)
    if len(matches) != 1:
        plan.conflicts.append(
            f"Row {row} has no unique registration identity. Match by Ticket Code or choose a new worksheet."
        )
        return None
    return matches[0]


def _adopt_legacy_rows(plan, legacy, id_rows, current_values):
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


def _write_current_registrations(plan, snapshot, current_values, id_rows, enabled, next_row):
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


def _mark_deleted(plan, snapshot, row, registration_id):
    column = plan.bindings["status"]
    if _cell(snapshot, row, column) != "Deleted":
        plan.cells[(row, column)] = "Deleted"
        plan.counts["deleted"] += 1
    plan.deleted_ids.append(registration_id)


def _plan_fingerprint(snapshot, fields, config, current_values, deleted_ids):
    return hashlib.sha256(
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


def plan_sync(snapshot, *, fields, current_values, deleted_ids, known_ids, event_id, config):
    plan = SyncPlan()
    _bind_columns(plan, snapshot, fields, event_id, config)
    enabled = [definition.key for definition in fields if definition.enabled]
    id_column = plan.bindings["registration_id"]
    existing_id_binding = _has_existing_id_binding(plan, snapshot, config)
    id_rows = {}
    legacy = []
    for row in range(config.header_row + 1, len(snapshot.values) + 1):
        registration_id = _cell(snapshot, row, id_column).strip()
        if registration_id:
            _check_identified_row(
                plan,
                row,
                registration_id,
                id_rows,
                current_values=current_values,
                known_ids=known_ids,
                deleted_ids=deleted_ids,
            )
            id_rows[registration_id] = row
            continue
        match = _match_unidentified_row(plan, snapshot, row, enabled, current_values, existing_id_binding)
        if match is not None:
            legacy.append((row, match))
    _adopt_legacy_rows(plan, legacy, id_rows, current_values)
    plan.requires_adoption = bool(plan.legacy_matches or plan.stale_rows)
    next_row = max(config.header_row, len(snapshot.values)) + 1
    _write_current_registrations(plan, snapshot, current_values, id_rows, enabled, next_row)
    for registration_id in deleted_ids:
        if registration_id in id_rows and registration_id in known_ids:
            _mark_deleted(plan, snapshot, id_rows[registration_id], registration_id)
    for stale in plan.stale_rows:
        _mark_deleted(plan, snapshot, stale["row"], stale["registration_id"])
    plan.fingerprint = _plan_fingerprint(snapshot, fields, config, current_values, deleted_ids)
    return plan
