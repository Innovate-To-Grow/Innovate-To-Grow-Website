from event.models import EventAgendaItem

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
