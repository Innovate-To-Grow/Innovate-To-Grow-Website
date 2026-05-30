from __future__ import annotations

from typing import Any

from .defaults import SECTION_DEFAULTS


def normalize_sheet_header(value: Any) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {normalize_sheet_header(key): value for key, value in record.items()}


def get_record_value(
    normalized_record: dict[str, Any],
    aliases: list[str],
    default: str = "",
) -> str:
    for alias in aliases:
        normalized_alias = normalize_sheet_header(alias)
        if normalized_alias in normalized_record:
            return str(normalized_record[normalized_alias] or "").strip()
    return default


def coerce_int(value: Any) -> int | None:
    normalized = str(value or "").strip()
    return int(normalized) if normalized.isdigit() else None


def normalize_section_code(*candidates: str) -> str:
    for value in candidates:
        normalized = "".join(character for character in str(value or "").upper() if character.isalnum())
        if not normalized:
            continue
        for code in SECTION_DEFAULTS:
            if normalized.startswith(code):
                return code
        if normalized.startswith("ENG"):
            return "ENGSL"
    return ""


def build_section_defaults(code: str) -> dict[str, Any]:
    defaults = SECTION_DEFAULTS.get(code, {})
    return {
        "code": code,
        "label": defaults.get("label", code),
        "display_order": defaults.get("display_order", len(SECTION_DEFAULTS)),
        "start_time": defaults.get("start_time", "1:00"),
        "slot_minutes": defaults.get("slot_minutes", 30),
        "accent_color": defaults.get("accent_color", "#002856"),
    }


def build_track_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for record in records:
        normalized = normalize_record(record)
        track_number = coerce_int(get_record_value(normalized, ["Track"]))
        section_code = normalize_section_code(get_record_value(normalized, ["Class"]))
        if track_number is None or not section_code:
            continue
        tracks.append(
            {
                "track_number": track_number,
                "section_code": section_code,
                "room": get_record_value(normalized, ["Room"]),
                "zoom_link": get_record_value(normalized, ["Zoom live", "Zoom"]),
                "topic": get_record_value(normalized, ["Topic"]),
                "winner": get_record_value(normalized, ["Winner"]),
                "label": f"Track {track_number}",
            }
        )
    return sorted(tracks, key=lambda item: item["track_number"])


def build_grand_winners(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    winners: list[dict[str, str]] = []
    for record in records:
        normalized = normalize_record(record)
        if get_record_value(normalized, ["Track"]).lower() != "award:":
            continue
        section_code = normalize_section_code(get_record_value(normalized, ["Class"]))
        winner = get_record_value(normalized, ["Winner"])
        if section_code and winner:
            winners.append({"section": section_code, "winner": winner})
    return winners


def build_slot_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for record in records:
        normalized = normalize_record(record)
        track_raw = get_record_value(normalized, ["Track"])
        order_raw = get_record_value(normalized, ["Order"])
        track_number = coerce_int(track_raw)
        slot_order = coerce_int(order_raw)
        is_fall = track_raw.strip().lower() == "(fall)"
        is_fall = is_fall or order_raw.strip().lower() == "(fall)"

        if not is_fall and (track_number is None or slot_order is None):
            continue

        team_number = get_record_value(normalized, ["Team#", "Team #", "Team Number", "Team"])
        team_name = get_record_value(normalized, ["TeamName", "Team Name"])
        project_title = get_record_value(normalized, ["Project Title", "Title"])
        organization = get_record_value(normalized, ["Organization", "Partner Organization", "Partner"])
        class_code = normalize_section_code(
            get_record_value(normalized, ["Class"]),
            team_number,
            team_name,
            project_title,
        )
        is_break = _is_break_slot(is_fall, team_name, project_title, organization)
        if not is_break and not team_number:
            continue

        slots.append(
            {
                "track_number": track_number,
                "slot_order": slot_order,
                "year_semester": get_record_value(normalized, ["Year-Semester", "Year Semester", "Semester"]),
                "class_code": class_code,
                "team_number": team_number,
                "team_name": team_name,
                "project_title": project_title,
                "organization": organization,
                "industry": get_record_value(normalized, ["Industry"]),
                "abstract": get_record_value(normalized, ["Abstract", "Project Abstract"]),
                "student_names": get_record_value(normalized, ["Student Names", "Students"]),
                "name_title": get_record_value(
                    normalized,
                    ["NameTitle", "Name Title", "Name: - Title:", "Contact Name Title"],
                ),
                "is_break": is_break,
                "is_presenting": not is_fall,
                "display_text": _display_text(team_number, team_name, project_title, is_break),
            }
        )
    return sorted(
        slots,
        key=lambda item: (
            not item["is_presenting"],
            item["track_number"] or 0,
            item["slot_order"] or 0,
            item["team_number"],
        ),
    )


def _is_break_slot(is_fall: bool, *values: str) -> bool:
    return (not is_fall) and any(value.lower() == "break" for value in values)


def _display_text(
    team_number: str,
    team_name: str,
    project_title: str,
    is_break: bool,
) -> str:
    if is_break:
        return "Break"
    return team_number or team_name or project_title or ""
