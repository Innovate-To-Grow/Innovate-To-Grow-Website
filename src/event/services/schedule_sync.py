from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.models import GoogleCredentialConfig
from event.models import (
    CurrentProject,
    CurrentProjectSchedule,
    EventAgendaItem,
    EventScheduleSection,
    EventScheduleSlot,
    EventScheduleTrack,
)

SECTION_DEFAULTS = {
    "CAP": {
        "label": "Engineering Capstone",
        "display_order": 0,
        "start_time": "1:00",
        "slot_minutes": 30,
        "accent_color": "#002856",
    },
    "CEE": {
        "label": "Civil & Environmental Engineering",
        "display_order": 1,
        "start_time": "1:00",
        "slot_minutes": 30,
        "accent_color": "#002856",
    },
    "CSE": {
        "label": "Software Engineering Capstone",
        "display_order": 2,
        "start_time": "1:00",
        "slot_minutes": 20,
        "accent_color": "#FFBF3C",
    },
    "ENGSL": {
        "label": "Engineering Service Learning",
        "display_order": 3,
        "start_time": "1:00",
        "slot_minutes": 30,
        "accent_color": "#002856",
    },
}

DEFAULT_AGENDA_ITEMS = [
    {
        "section_type": EventAgendaItem.SectionType.EXPO,
        "time_label": "9:00",
        "title": "Registration and Coffee",
        "location": "Gym (only, NO Zoom)",
        "display_order": 0,
    },
    {
        "section_type": EventAgendaItem.SectionType.EXPO,
        "time_label": "10:00",
        "title": "Expo - Posters - Demos - Lunch",
        "location": "Gym (only, NO Zoom)",
        "display_order": 1,
    },
    {
        "section_type": EventAgendaItem.SectionType.AWARDS,
        "time_label": "4:45",
        "title": "Award Ceremony",
        "location": "Gym",
        "display_order": 0,
    },
    {
        "section_type": EventAgendaItem.SectionType.AWARDS,
        "time_label": "5:15",
        "title": "Reception",
        "location": "Gym",
        "display_order": 1,
    },
]


class ScheduleSyncError(Exception):
    """Raised when schedule data cannot be fetched or imported."""


@dataclass
class ScheduleSyncStats:
    sections_created: int = 0
    tracks_created: int = 0
    slots_created: int = 0
    agenda_items_created: int = 0
    unmatched_slots: int = 0
    break_slots: int = 0


def _normalize_sheet_header(value: Any) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {_normalize_sheet_header(key): value for key, value in record.items()}


def _get_record_value(normalized_record: dict[str, Any], aliases: list[str], default: str = "") -> str:
    for alias in aliases:
        normalized_alias = _normalize_sheet_header(alias)
        if normalized_alias in normalized_record:
            return str(normalized_record[normalized_alias] or "").strip()
    return default


def _coerce_int(value: Any) -> int | None:
    normalized = str(value or "").strip()
    return int(normalized) if normalized.isdigit() else None


def _normalize_section_code(*candidates: str) -> str:
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


def _build_section_defaults(code: str) -> dict[str, Any]:
    defaults = SECTION_DEFAULTS.get(code, {})
    return {
        "code": code,
        "label": defaults.get("label", code),
        "display_order": defaults.get("display_order", len(SECTION_DEFAULTS)),
        "start_time": defaults.get("start_time", "1:00"),
        "slot_minutes": defaults.get("slot_minutes", 30),
        "accent_color": defaults.get("accent_color", "#002856"),
    }


def _get_worksheet_by_gid(spreadsheet, worksheet_gid: int):
    return next((worksheet for worksheet in spreadsheet.worksheets() if worksheet.id == worksheet_gid), None)


def fetch_schedule_sheet_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = CurrentProjectSchedule.load()
    if not source or not source.sheet_id or not source.tracks_gid or not source.projects_gid:
        raise ScheduleSyncError("Google Sheets source is not fully configured for this event.")

    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise ScheduleSyncError("No active Google service account is configured.")

    try:
        import gspread

        client = gspread.service_account_from_dict(credentials.get_credentials_info())
        spreadsheet = client.open_by_key(source.sheet_id)
        tracks_worksheet = _get_worksheet_by_gid(spreadsheet, int(source.tracks_gid))
        projects_worksheet = _get_worksheet_by_gid(spreadsheet, int(source.projects_gid))
    except Exception as exc:  # pragma: no cover - exercised via service tests with mocked fetch
        raise ScheduleSyncError(f"Unable to open the configured Google Sheet: {exc}") from exc

    if tracks_worksheet is None:
        raise ScheduleSyncError("Schedule tracks worksheet not found.")
    if projects_worksheet is None:
        raise ScheduleSyncError("Schedule projects worksheet not found.")

    try:
        return tracks_worksheet.get_all_records(), projects_worksheet.get_all_records()
    except Exception as exc:  # pragma: no cover - exercised via service tests with mocked fetch
        raise ScheduleSyncError(f"Unable to read schedule worksheet records: {exc}") from exc


def _build_track_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for record in records:
        normalized = _normalize_record(record)
        track_number = _coerce_int(_get_record_value(normalized, ["Track"]))
        if track_number is None:
            continue
        section_code = _normalize_section_code(_get_record_value(normalized, ["Class"]))
        if not section_code:
            continue
        tracks.append(
            {
                "track_number": track_number,
                "section_code": section_code,
                "room": _get_record_value(normalized, ["Room"]),
                "zoom_link": _get_record_value(normalized, ["Zoom live", "Zoom"]),
                "topic": _get_record_value(normalized, ["Topic"]),
                "winner": _get_record_value(normalized, ["Winner"]),
                "label": f"Track {track_number}",
            }
        )
    return sorted(tracks, key=lambda item: item["track_number"])


def _build_grand_winners(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    winners: list[dict[str, str]] = []
    for record in records:
        normalized = _normalize_record(record)
        track_value = _get_record_value(normalized, ["Track"])
        if track_value.lower() != "award:":
            continue
        section_code = _normalize_section_code(_get_record_value(normalized, ["Class"]))
        winner = _get_record_value(normalized, ["Winner"])
        if section_code and winner:
            winners.append({"section": section_code, "winner": winner})
    return winners


def _build_slot_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for record in records:
        normalized = _normalize_record(record)
        track_number = _coerce_int(_get_record_value(normalized, ["Track"]))
        slot_order = _coerce_int(_get_record_value(normalized, ["Order"]))
        if track_number is None or slot_order is None:
            continue

        team_number = _get_record_value(normalized, ["Team#", "Team #", "Team Number", "Team"])
        team_name = _get_record_value(normalized, ["TeamName", "Team Name"])
        project_title = _get_record_value(normalized, ["Project Title", "Title"])
        organization = _get_record_value(normalized, ["Organization", "Partner Organization", "Partner"])
        class_code = _normalize_section_code(
            _get_record_value(normalized, ["Class"]),
            team_number,
            team_name,
            project_title,
        )
        is_break = any(value.lower() == "break" for value in [team_name, project_title, organization])
        if not is_break and not any([team_number, team_name, project_title, organization]):
            continue

        display_text = team_number or team_name or project_title or ("Break" if is_break else "")
        slots.append(
            {
                "track_number": track_number,
                "slot_order": slot_order,
                "year_semester": _get_record_value(normalized, ["Year-Semester", "Year Semester", "Semester"]),
                "class_code": class_code,
                "team_number": team_number,
                "team_name": team_name,
                "project_title": project_title,
                "organization": organization,
                "industry": _get_record_value(normalized, ["Industry"]),
                "abstract": _get_record_value(normalized, ["Abstract", "Project Abstract"]),
                "student_names": _get_record_value(normalized, ["Student Names", "Students"]),
                "name_title": _get_record_value(
                    normalized,
                    ["NameTitle", "Name Title", "Name: - Title:", "Contact Name Title"],
                ),
                "is_break": is_break,
                "display_text": "Break" if is_break else display_text,
            }
        )
    return sorted(slots, key=lambda item: (item["track_number"], item["slot_order"], item["team_number"]))


def _sync_projects_from_slots(
    config: CurrentProjectSchedule, parsed_slots: list[dict[str, Any]]
) -> dict[tuple[str, str], CurrentProject]:
    """Create/update CurrentProject records for the given config and return a lookup dict."""
    lookup: dict[tuple[str, str], CurrentProject] = {}

    for slot in parsed_slots:
        if slot["is_break"]:
            continue
        title = slot["project_title"]
        if not title or title.lower() == "break":
            continue

        team_number = slot["team_number"].strip()
        section_code = _normalize_section_code(slot["class_code"])

        project, _ = CurrentProject.objects.update_or_create(
            schedule=config,
            team_number=team_number,
            project_title=title,
            defaults={
                "class_code": slot["class_code"],
                "team_name": slot["team_name"],
                "organization": slot["organization"],
                "industry": slot["industry"],
                "abstract": slot["abstract"],
                "student_names": slot["student_names"],
            },
        )

        key = (section_code, team_number.upper())
        if key[0] and key[1] and key not in lookup:
            lookup[key] = project

    return lookup


def sync_schedule(
    config: CurrentProjectSchedule,
    *,
    tracks_records: list[dict[str, Any]] | None = None,
    projects_records: list[dict[str, Any]] | None = None,
) -> ScheduleSyncStats:
    try:
        if tracks_records is None or projects_records is None:
            tracks_records, projects_records = fetch_schedule_sheet_records()

        parsed_tracks = _build_track_rows(tracks_records)
        grand_winners = _build_grand_winners(tracks_records)
        parsed_slots = _build_slot_rows(projects_records)
        if not parsed_tracks or not parsed_slots:
            raise ScheduleSyncError("The configured sheet does not contain any schedule tracks or slots.")

        current_projects = _sync_projects_from_slots(config, parsed_slots)
        stats = ScheduleSyncStats()

        with transaction.atomic():
            EventScheduleSlot.objects.filter(track__section__config=config).delete()
            EventScheduleTrack.objects.filter(section__config=config).delete()
            EventScheduleSection.objects.filter(config=config).delete()
            EventAgendaItem.objects.filter(config=config).delete()
            CurrentProject.objects.filter(schedule=config).exclude(
                pk__in=[p.pk for p in current_projects.values()]
            ).delete()

            sections_by_code: dict[str, EventScheduleSection] = {}
            for code in sorted(
                {
                    *(track["section_code"] for track in parsed_tracks if track["section_code"]),
                    *(slot["class_code"] for slot in parsed_slots if slot["class_code"]),
                },
                key=lambda item: (_build_section_defaults(item)["display_order"], item),
            ):
                section = EventScheduleSection.objects.create(config=config, **_build_section_defaults(code))
                sections_by_code[code] = section
                stats.sections_created += 1

            tracks_by_number: dict[int, EventScheduleTrack] = {}
            section_track_counts: dict[str, int] = {}
            for track in parsed_tracks:
                section = sections_by_code[track["section_code"]]
                display_order = section_track_counts.get(section.code, 0)
                section_track_counts[section.code] = display_order + 1
                track_obj = EventScheduleTrack.objects.create(
                    section=section,
                    track_number=track["track_number"],
                    label=track["label"],
                    room=track["room"],
                    zoom_link=track["zoom_link"],
                    topic=track["topic"],
                    winner=track["winner"],
                    display_order=display_order,
                )
                tracks_by_number[track_obj.track_number] = track_obj
                stats.tracks_created += 1

            for slot in parsed_slots:
                track = tracks_by_number.get(slot["track_number"])
                if track is None:
                    continue
                project = current_projects.get((slot["class_code"], slot["team_number"].upper()))
                EventScheduleSlot.objects.create(
                    track=track,
                    project=project,
                    slot_order=slot["slot_order"],
                    is_break=slot["is_break"],
                    year_semester=slot["year_semester"],
                    class_code=slot["class_code"],
                    team_number=slot["team_number"],
                    team_name=slot["team_name"],
                    project_title=slot["project_title"],
                    organization=slot["organization"],
                    industry=slot["industry"],
                    abstract=slot["abstract"],
                    student_names=slot["student_names"],
                    name_title=slot["name_title"],
                    display_text=slot["display_text"],
                )
                stats.slots_created += 1
                if slot["is_break"]:
                    stats.break_slots += 1
                elif project is None:
                    stats.unmatched_slots += 1

            for agenda_item in DEFAULT_AGENDA_ITEMS:
                EventAgendaItem.objects.create(config=config, **agenda_item)
                stats.agenda_items_created += 1

        CurrentProjectSchedule.objects.filter(pk=config.pk).update(
            last_synced_at=timezone.now(),
            sync_error="",
            grand_winners=grand_winners,
        )

        from django.core.cache import cache

        cache.delete("event:current-projects")

        return stats
    except Exception as exc:
        error_message = str(exc)
        if config.pk:
            CurrentProjectSchedule.objects.filter(pk=config.pk).update(sync_error=error_message[:4000])
        if isinstance(exc, ScheduleSyncError):
            raise
        raise ScheduleSyncError(error_message) from exc
