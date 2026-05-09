from __future__ import annotations

from typing import Any

from event.models import (
    CurrentProject,
    CurrentProjectSchedule,
    EventAgendaItem,
    EventScheduleSection,
    EventScheduleSlot,
    EventScheduleTrack,
)

from ..defaults import DEFAULT_AGENDA_ITEMS
from ..parsing import build_section_defaults
from ..shared import ScheduleSyncStats


def clear_schedule(
    config: CurrentProjectSchedule,
    touched_project_pks: set[Any],
) -> None:
    EventScheduleSlot.objects.filter(track__section__config=config).delete()
    EventScheduleTrack.objects.filter(section__config=config).delete()
    EventScheduleSection.objects.filter(config=config).delete()
    EventAgendaItem.objects.filter(config=config).delete()
    CurrentProject.objects.filter(schedule=config).exclude(pk__in=touched_project_pks).delete()


def create_sections(
    config: CurrentProjectSchedule,
    parsed_tracks: list[dict[str, Any]],
    parsed_slots: list[dict[str, Any]],
    stats: ScheduleSyncStats,
) -> dict[str, EventScheduleSection]:
    sections_by_code: dict[str, EventScheduleSection] = {}
    section_codes = {
        *(track["section_code"] for track in parsed_tracks if track["section_code"]),
        *(slot["class_code"] for slot in parsed_slots if slot["class_code"]),
    }
    for code in sorted(section_codes, key=_section_sort_key):
        section = EventScheduleSection.objects.create(
            config=config,
            **build_section_defaults(code),
        )
        sections_by_code[code] = section
        stats.sections_created += 1
    return sections_by_code


def create_tracks(
    sections_by_code: dict[str, EventScheduleSection],
    parsed_tracks: list[dict[str, Any]],
    stats: ScheduleSyncStats,
) -> dict[int, EventScheduleTrack]:
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
    return tracks_by_number


def create_slots(
    tracks_by_number: dict[int, EventScheduleTrack],
    current_projects: dict[tuple[str, str], CurrentProject],
    parsed_slots: list[dict[str, Any]],
    stats: ScheduleSyncStats,
) -> None:
    for slot in parsed_slots:
        if not slot["is_presenting"]:
            continue
        track = tracks_by_number.get(slot["track_number"])
        if track is None:
            continue
        project = current_projects.get((slot["class_code"], slot["team_number"].upper()))
        EventScheduleSlot.objects.create(track=track, project=project, **_slot_defaults(slot))
        stats.slots_created += 1
        if slot["is_break"]:
            stats.break_slots += 1
        elif project is None:
            stats.unmatched_slots += 1


def create_agenda_items(
    config: CurrentProjectSchedule,
    stats: ScheduleSyncStats,
) -> None:
    for agenda_item in DEFAULT_AGENDA_ITEMS:
        EventAgendaItem.objects.create(config=config, **agenda_item)
        stats.agenda_items_created += 1


def _section_sort_key(code: str) -> tuple[int, str]:
    return build_section_defaults(code)["display_order"], code


def _slot_defaults(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_order": slot["slot_order"],
        "is_break": slot["is_break"],
        "year_semester": slot["year_semester"],
        "class_code": slot["class_code"],
        "team_number": slot["team_number"],
        "team_name": slot["team_name"],
        "project_title": slot["project_title"],
        "organization": slot["organization"],
        "industry": slot["industry"],
        "abstract": slot["abstract"],
        "student_names": slot["student_names"],
        "name_title": slot["name_title"],
        "display_text": slot["display_text"],
    }
