"""Keeping a managed worksheet's developer metadata to one entry per purpose.

A managed worksheet carries, under this event's keys, one entry per bound column, one header-row marker and one entry
per configured label. Google allows 30,000 characters of developer metadata per sheet, so a sync deletes, in the same
write, every entry of this event it does not need: copies, left by syncs that could not read row and column metadata
and so bound every column again on each run; bindings and labels of fields that no longer exist (deleted questions);
and markers of a header row that is no longer configured. Entries it cannot attribute safely stay, and the planner
reports them as conflicts.
"""

import json
from collections import defaultdict

from .snapshot import HEADER_MARKER, LABEL_METADATA_PREFIX, METADATA_PREFIX, _cell, normalized_label


def _span(entry):
    return entry.get("location", {}).get("dimensionRange", {})


def _place(entry):
    span = _span(entry)
    return span.get("dimension"), span.get("startIndex", 0), span.get("endIndex")


def _by_place(entries):
    places = defaultdict(list)
    for entry in entries:
        places[_place(entry)].append(entry)
    return places


def _all_but(entries, keep):
    return [entry["metadataId"] for entry in entries if entry is not keep]


def _copies(places):
    """Every entry but the first at each place: exact copies that carry nothing the first one does not."""
    return [identity for entries in places.values() for identity in _all_but(entries, entries[0])]


def _label_setting(entry):
    try:
        setting = json.loads(entry.get("metadataValue", ""))
    except (TypeError, ValueError):
        return {}
    return setting if isinstance(setting, dict) and isinstance(setting.get("key"), str) else {}


def _shows_field(snapshot, header_row, place, definition):
    """Whether the column at ``place`` is headed by one of the field's labels."""
    dimension, start, end = place
    if dimension != "COLUMNS" or end != start + 1:
        return False
    labels = {normalized_label(label) for label in (definition.label, *definition.aliases)}
    return normalized_label(_cell(snapshot, header_row, start + 1)) in labels


def _redundant_bindings(entries, definition, snapshot, header_row):
    if definition is None:
        # The field no longer exists (a deleted question): its column stays as it is, no longer managed.
        return _all_but(entries, None)
    places = _by_place(entries)
    if len(places) > 1:
        # Earlier syncs bound the field again wherever its label stood. Keep the column still headed by the field
        # (where they wrote last); with no single such column the planner reports the duplicate binding.
        shown = [place for place in places if _shows_field(snapshot, header_row, place, definition)]
        if len(shown) == 1:
            return _all_but(entries, places[shown[0]][0])
    return _copies(places)


def _redundant_markers(markers, header_row):
    places = _by_place(markers)
    configured = ("ROWS", header_row - 1, header_row)
    if configured in places:
        return _all_but(markers, places[configured][0])
    return _copies(places)


def _redundant_labels(entries, definition):
    if definition is None:
        return _all_but(entries, None)
    # Keep the entry recording the label configured now, so the header is not rewritten over a later rename.
    configured = definition.label if definition.explicit_label else ""
    keep = next((entry for entry in entries if _label_setting(entry).get("label") == configured), entries[0])
    return _all_but(entries, keep)


def redundant_metadata(snapshot, fields, *, event_id, header_row):
    """Ids of this event's developer metadata on the worksheet that a sync deletes before writing."""
    own_key, label_key = f"{METADATA_PREFIX}{event_id}", f"{LABEL_METADATA_PREFIX}{event_id}"
    definitions = {definition.key: definition for definition in fields}
    markers, bindings, labels = [], defaultdict(list), defaultdict(list)
    # Lowest id first, so every read of the same worksheet keeps the same entry.
    for entry in sorted(snapshot.metadata, key=lambda item: item.get("metadataId") or 0):
        key, value = entry.get("metadataKey"), entry.get("metadataValue", "")
        if entry.get("metadataId") is None or _span(entry).get("sheetId") != snapshot.sheet_id:
            continue
        if key == own_key and value == HEADER_MARKER:
            markers.append(entry)
        elif key == own_key and value:
            bindings[value].append(entry)
        elif key == label_key and (setting := _label_setting(entry)):
            labels[setting["key"]].append(entry)
    removed = _redundant_markers(markers, header_row)
    for field_key, entries in bindings.items():
        removed += _redundant_bindings(entries, definitions.get(field_key), snapshot, header_row)
    for field_key, entries in labels.items():
        removed += _redundant_labels(entries, definitions.get(field_key))
    return removed
