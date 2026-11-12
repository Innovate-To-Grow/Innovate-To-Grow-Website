"""Compare a sheet's rows with each other.

``cross_row_drops`` sets aside the Secondary Email and Phone Number cells that can't be applied, each with a warning:
a malformed address (V2), a number that is not a 10-digit US number (V4), a secondary equal to the row's own primary
(V7), and a cell another row already uses (V8): one row's Primary Email wins over another row's Secondary Email, and a
new address or number named by two rows is added by the first one only.

``duplicate_groups`` finds the rows that are the same person (C1): rows that resolve to the same member, through any
address or the Member UUID, and rows that would create the same new address.
"""

from __future__ import annotations

from collections import defaultdict

from ..contacts import valid_new_address
from .lookup import Snapshot, address_key, us_phone

_GROUPABLE_STATUSES = frozenset({"ready_create", "ready_update"})
_GROUPABLE_CONFLICTS = frozenset({"name_differs", "address_not_primary", "unlinked_address", "exists_but_skip_mode"})


def cross_row_drops(rows: list[dict], snapshot: Snapshot) -> dict[int, dict[str, dict]]:
    """``{row number: {cell key: {"code", "text"}}}`` for every cell set aside."""
    primary_rows: dict[str, int] = {}
    for row in rows:
        address = row.get("primary_email")
        # Only a primary the row can import wins over another row's Secondary cell.
        if address and (snapshot.email_records(address) or valid_new_address(address)):
            primary_rows.setdefault(address_key(address), row["row"])
    drops: dict[int, dict[str, dict]] = defaultdict(dict)
    new_secondaries: dict[str, int] = {}
    new_phones: dict[str, int] = {}
    for row in rows:
        if row.get("secondary_email"):
            warning = _secondary_drop(row, primary_rows, new_secondaries, snapshot)
            if warning:
                drops[row["row"]]["secondary_email"] = warning
        if row.get("phone_number"):
            warning = _phone_drop(row, new_phones, snapshot)
            if warning:
                drops[row["row"]]["phone_number"] = warning
    return dict(drops)


def _secondary_drop(row: dict, primary_rows: dict, new_secondaries: dict, snapshot: Snapshot) -> dict | None:
    address = row["secondary_email"]
    key = address_key(address)
    if row.get("primary_email") and key == address_key(row["primary_email"]):
        return {"code": "V7", "text": "Secondary Email is the same as the Primary Email; ignored"}
    other = primary_rows.get(key)
    if other is not None and other != row["row"]:
        return {
            "code": "V8",
            "text": f"Secondary Email {address} is the Primary Email of row {other}; that row wins, and this cell is "
            "ignored",
        }
    records = snapshot.email_records(address)
    # A stored address held by a member (or by several records that differ only in case) is never added: each row
    # reports that on its own. One contact email with no member is taken by the row that attaches it, so like a new
    # address it may be added by one row only: a second claim would fail the whole apply.
    if records and not (len(records) == 1 and records[0].member is None):
        return None
    if not records and not valid_new_address(address):
        return {"code": "V2", "text": f"Secondary Email {address!r} is not a valid email address; ignored"}
    first = new_secondaries.setdefault(key, row["row"])
    if first != row["row"]:
        return {"code": "V8", "text": f"Secondary Email {address} is also in row {first}; only that row adds it"}
    return None


def _phone_drop(row: dict, new_phones: dict, snapshot: Snapshot) -> dict | None:
    parsed = us_phone(row["phone_number"])
    if parsed is None:
        return {"code": "V4", "text": f"Phone Number {row['phone_number']} is not a 10-digit US number; ignored"}
    if parsed[0] in snapshot.phones:
        return None
    first = new_phones.setdefault(parsed[0], row["row"])
    if first != row["row"]:
        e164 = f"+{parsed[1].split('-')[0]}{parsed[0]}"
        return {"code": "V8", "text": f"Phone Number {e164} is also in row {first}; only that row adds it"}
    return None


def duplicate_groups(rows: list[dict], resolutions) -> dict[int, list[int]]:
    """``{row number: the row numbers of its group}`` for every row that shares its person with another row."""
    parent: dict[int, int] = {}

    def find(number: int) -> int:
        while parent[number] != number:
            parent[number] = parent[parent[number]]
            number = parent[number]
        return number

    first_with: dict[tuple, int] = {}
    for row, resolution in zip(rows, resolutions, strict=True):
        if resolution.status not in _GROUPABLE_STATUSES and resolution.conflict not in _GROUPABLE_CONFLICTS:
            continue
        number = row["row"]
        parent[number] = number
        keys = [("address", address_key(row["primary_email"]))]
        if resolution.target:
            keys.append(("member", resolution.target))
        for key in keys:
            if key in first_with:
                parent[find(number)] = find(first_with[key])
            else:
                first_with[key] = number
    groups: dict[int, list[int]] = defaultdict(list)
    for number in parent:
        groups[find(number)].append(number)
    return {number: sorted(members) for members in groups.values() if len(members) > 1 for number in members}
