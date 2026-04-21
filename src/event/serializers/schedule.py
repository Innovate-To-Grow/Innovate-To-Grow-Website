from __future__ import annotations

from collections import defaultdict

from event.models import CurrentProjectSchedule, EventAgendaItem


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


def build_schedule_payload(config: CurrentProjectSchedule) -> dict:
    sections = []
    project_rows = []

    for section in config.schedule_sections.all():
        slot_map = defaultdict(list)
        max_order = 0
        tracks = list(section.tracks.all())
        for track in tracks:
            for slot in track.slots.select_related("project").all():
                slot_map[track.pk].append(slot)
                max_order = max(max_order, slot.slot_order)
                if slot.is_break:
                    continue
                project_rows.append(
                    {
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
                        "tooltip": slot.name_title,
                    }
                )

        sections.append(
            {
                "id": str(section.pk),
                "code": section.code,
                "label": section.label,
                "display_order": section.display_order,
                "start_time": section.start_time,
                "slot_minutes": section.slot_minutes,
                "accent_color": section.accent_color,
                "max_order": max_order,
                "tracks": [
                    {
                        "id": str(track.pk),
                        "track_number": track.track_number,
                        "label": track.label,
                        "room": track.room,
                        "zoom_link": track.zoom_link,
                        "topic": track.topic,
                        "winner": track.winner,
                        "display_order": track.display_order,
                        "slots": [
                            {
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
                            for slot in slot_map[track.pk]
                        ],
                    }
                    for track in tracks
                ],
            }
        )

    project_rows.sort(key=lambda row: (row["track"], row["order"], row["team_number"]))

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
