from __future__ import annotations

from collections import defaultdict

from apps.event.models import CurrentProjectSchedule, EventAgendaItem


def _serialize_agenda_group(config: CurrentProjectSchedule, section_type: str, title: str) -> dict:
    items = [item for item in config.agenda_items.all() if item.section_type == section_type]
    location = items[0].location if items else ""
    return {
        "title": title,
        "location": location,
        "items": [
            {
                "id": str(item.pk),
                "time": item.time_label,
                "title": item.title,
                "location": item.location,
            }
            for item in items
        ],
    }


def _scheduled_project_row(track, slot) -> dict:
    return {
        "id": str(slot.pk),
        "track": track.track_number,
        "order": slot.slot_order,
        "year_semester": slot.year_semester,
        "class_code": slot.class_code,
        "team_number": slot.team_number,
        "team_name": slot.team_name,
        "project_title": slot.project_title,
        "organization": slot.organization,
        "industry": slot.industry,
        "abstract": slot.abstract,
        "student_names": slot.student_names,
        "is_presenting": slot.project.is_presenting if slot.project else True,
        "tooltip": slot.name_title,
    }


def _unscheduled_project_row(project) -> dict:
    return {
        "id": str(project.pk),
        "track": 0,
        "order": 0,
        "year_semester": "",
        "class_code": project.class_code,
        "team_number": project.team_number,
        "team_name": project.team_name,
        "project_title": project.project_title,
        "organization": project.organization,
        "industry": project.industry,
        "abstract": project.abstract,
        "student_names": project.student_names,
        "is_presenting": False,
        "tooltip": "",
    }


def _slot_payload(slot) -> dict:
    return {
        "id": str(slot.pk),
        "order": slot.slot_order,
        "is_break": slot.is_break,
        "display_text": slot.display_text,
        "team_number": slot.team_number,
        "team_name": slot.team_name,
        "project_title": slot.project_title,
        "organization": slot.organization,
        "industry": slot.industry,
        "abstract": slot.abstract,
        "student_names": slot.student_names,
        "tooltip": slot.name_title,
        "project_id": str(slot.project_id) if slot.project_id else None,
        "is_presenting": slot.project.is_presenting if slot.project else None,
    }


def _track_payload(track, slots) -> dict:
    return {
        "id": str(track.pk),
        "track_number": track.track_number,
        "label": track.label,
        "room": track.room,
        "zoom_link": track.zoom_link,
        "topic": track.topic,
        "winner": track.winner,
        "display_order": track.display_order,
        "slots": [_slot_payload(slot) for slot in slots],
    }


def _section_payload(section, project_rows: list) -> dict:
    """One class's presentation grid; appends each presenting slot's project row to ``project_rows``."""
    slot_map = defaultdict(list)
    max_order = 0
    tracks = list(section.tracks.all())
    for track in tracks:
        for slot in track.slots.select_related("project").all():
            slot_map[track.pk].append(slot)
            max_order = max(max_order, slot.slot_order)
            if not slot.is_break:
                project_rows.append(_scheduled_project_row(track, slot))
    return {
        "id": str(section.pk),
        "code": section.code,
        "label": section.label,
        "display_order": section.display_order,
        "start_time": section.start_time,
        "slot_minutes": section.slot_minutes,
        "accent_color": section.accent_color,
        "max_order": max_order,
        "tracks": [_track_payload(track, slot_map[track.pk]) for track in tracks],
    }


def build_schedule_payload(config: CurrentProjectSchedule) -> dict:
    project_rows = []
    sections = [_section_payload(section, project_rows) for section in config.schedule_sections.all()]
    project_rows.sort(key=lambda row: (row["track"], row["order"], row["team_number"]))
    for project in config.projects.filter(is_presenting=False).order_by("class_code", "team_number"):
        project_rows.append(_unscheduled_project_row(project))

    return {
        "event": {
            "id": str(config.pk),
            "name": config.name,
        },
        "show_winners": config.show_winners,
        "grand_winners": config.grand_winners or [],
        "expo": _serialize_agenda_group(config, EventAgendaItem.SectionType.EXPO, "EXPO: POSTERS AND DEMOS"),
        "presentations_title": "PRESENTATIONS",
        "sections": sections,
        "awards": _serialize_agenda_group(config, EventAgendaItem.SectionType.AWARDS, "AWARDS & RECEPTION"),
        "projects": project_rows,
    }
