"""Parsing helpers for member import spreadsheets."""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import date, datetime

from django.utils import timezone

from .columns import (
    _EXPORT_ESCAPED,
    _TEXT_KEYS,
    DATE_FORMATS,
    FALSE_TEXT,
    FLAG_COLUMNS,
    HEADER_MAP,
    IGNORED_COLUMNS,
    IMPORTED_KEYS,
    # Re-exported: the import tests read it from here.
    PHONE_VERIFIED_IGNORED,  # noqa: F401
    TRUE_TEXT,
)


def generate_random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def normalize_header(header: str) -> str:
    if not header:
        return ""
    return HEADER_MAP.get(str(header).strip().lower(), str(header).strip().lower())


def clean_text(value) -> str:
    """A text cell, trimmed, with the apostrophe our own export put before ``= + - @`` taken off again."""
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > 1 and text[0] == "'" and text[1] in _EXPORT_ESCAPED:
        return text[1:]
    return text


def cell_text(value) -> str:
    """How a cell reads in the review: the text as typed, ``TRUE``/``FALSE`` for a boolean, ``""`` when empty."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def column_notes(headers) -> list[str]:
    """The notes for the ``IGNORED_COLUMNS`` among ``headers`` (normalised): what the import does instead."""
    return [note for key, note in IGNORED_COLUMNS.items() if key in headers]


def parse_flag(value) -> bool | None:
    """Read a TRUE/FALSE cell: True, False, or None for a blank cell and for text that is neither.

    Unrecognised text ("N/A", "x", "?") used to count as FALSE, which un-verified or unsubscribed contacts on a
    typo. Now it counts as blank, which leaves the stored value alone.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return {1: True, 0: False}.get(value)
    text = str(value).strip().lower() if value is not None else ""
    if text in TRUE_TEXT:
        return True
    if text in FALSE_TEXT:
        return False
    return None


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    str_val = str(value).strip()
    if not str_val:
        return None
    for fmt in DATE_FORMATS:
        try:
            return timezone.make_aware(datetime.strptime(str_val, fmt))
        except ValueError:
            continue
    return None


def clean_phone(value) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    # Remove trailing ".0" from Excel numeric conversion
    if stripped.endswith(".0"):
        stripped = stripped[:-2]
    # Strip non-digit characters except leading +
    digits_only = "".join(c for c in stripped if c.isdigit())
    if not digits_only:
        return None
    # Normalize to E.164 format (preserve leading +)
    if stripped.startswith("+"):
        return f"+{digits_only}"
    return f"+{digits_only}"


def optional_flag(row_data: dict, key: str, notes: list[str] | None = None) -> bool | None:
    """Return the boolean in ``key``, or None when the sheet does not supply one.

    A missing column, a blank cell and unrecognised text all give None, which keeps the stored value. Reading these
    columns as FALSE instead turned "this sheet has no Primary Verified column" into "set verified=False", which
    de-verified the primary email of every matched member and locked them out of every login path. Unrecognised
    text is reported in ``notes``.
    """
    value = row_data.get(key)
    flag = parse_flag(value)
    if flag is None and notes is not None and str(value if value is not None else "").strip():
        notes.append(f"{FLAG_COLUMNS[key]} cell {str(value).strip()!r} is not TRUE or FALSE; it was ignored")
    return flag


def _member_uuid(row_data: dict) -> tuple[str | None, str]:
    """``(canonical UUID or None, the cell's text)``; text that is not a UUID gives None with the text kept."""
    text = clean_text(row_data.get("member_uuid"))
    if not text:
        return None, ""
    try:
        return str(uuid.UUID(text)), text
    except ValueError:
        return None, text


def _when_started(row_data: dict, warnings: list[dict]):
    value = row_data.get("when_started")
    parsed = parse_date(value)
    if parsed is None and cell_text(value):
        warnings.append({"code": "V6", "text": f"When Started cell {cell_text(value)!r} is not a date; it was ignored"})
    return parsed


def parse_row(row_num: int, row_data: dict) -> dict:
    """One data row as the import reads it. Blank cells and missing columns become ``""`` or None ("not supplied")."""
    notes: list[str] = []
    flags = {key: optional_flag(row_data, key, notes) for key in FLAG_COLUMNS}
    warnings = [{"code": "V5", "text": note} for note in notes]
    date_joined = _when_started(row_data, warnings)
    member_uuid, member_uuid_text = _member_uuid(row_data)
    return {
        "row": row_num,
        "primary_email": clean_text(row_data.get("primary_email")) or None,
        **{key: clean_text(row_data.get(key)) for key in _TEXT_KEYS},
        "date_joined": date_joined,
        "secondary_email": clean_text(row_data.get("secondary_email")) or None,
        "phone_number": clean_phone(row_data.get("phone_number")),
        **flags,
        # Header presence, not cell content. Neither a blank cell nor a missing column deletes anything; a blank
        # cell in a column the sheet has is reported, so whoever expected the old "blank clears it" behaviour sees
        # what was kept (and, in the review, can tick its removal).
        "has_secondary_email_column": "secondary_email" in row_data,
        "has_phone_column": "phone_number" in row_data,
        "member_uuid": member_uuid,
        "member_uuid_text": member_uuid_text,
        # What the row's cells could not say: reported only if the row is imported.
        "notes": [warning["text"] for warning in warnings],
        "warnings": warnings,
        # Every imported cell as typed, for the review page.
        "raw": {key: cell_text(value) for key, value in row_data.items() if key in IMPORTED_KEYS},
    }


def values_to_json(parsed: dict) -> dict:
    """``parse_row``'s output in a form a JSONField stores (the date as ISO text)."""
    values = dict(parsed)
    if values.get("date_joined") is not None:
        values["date_joined"] = values["date_joined"].isoformat()
    return values


def values_from_json(values: dict) -> dict:
    """The inverse of ``values_to_json``."""
    parsed = dict(values)
    if parsed.get("date_joined"):
        parsed["date_joined"] = datetime.fromisoformat(parsed["date_joined"])
    return parsed
