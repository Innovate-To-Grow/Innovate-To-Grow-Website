"""Safe section-hide presets for CMS embed widgets."""

from django.core.exceptions import ValidationError

GENERIC_HIDDEN_SECTION_PRESETS = [
    {
        "key": "section_titles",
        "label": "Section titles",
        "routes": [],
    },
]

ROUTE_HIDDEN_SECTION_PRESETS = {
    "/schedule": [
        {
            "key": "schedule_header",
            "label": "Schedule header",
            "routes": ["/schedule"],
        },
        {
            "key": "schedule_winners",
            "label": "Winners",
            "routes": ["/schedule"],
        },
        {
            "key": "schedule_expo",
            "label": "Expo",
            "routes": ["/schedule"],
        },
        {
            "key": "schedule_presentations",
            "label": "Presentations",
            "routes": ["/schedule"],
        },
        {
            "key": "schedule_awards",
            "label": "Awards",
            "routes": ["/schedule"],
        },
        {
            "key": "schedule_projects",
            "label": "Projects & Teams",
            "routes": ["/schedule"],
        },
    ],
}


def all_hidden_section_presets():
    presets = list(GENERIC_HIDDEN_SECTION_PRESETS)
    for route_presets in ROUTE_HIDDEN_SECTION_PRESETS.values():
        presets.extend(route_presets)
    return presets


def hidden_section_choices():
    return [(preset["key"], preset["label"]) for preset in all_hidden_section_presets()]


def hidden_section_presets_payload():
    return [
        {
            "key": preset["key"],
            "label": preset["label"],
            "routes": list(preset.get("routes") or []),
        }
        for preset in all_hidden_section_presets()
    ]


def allowed_hidden_section_keys(widget_type, app_route):
    keys = {preset["key"] for preset in GENERIC_HIDDEN_SECTION_PRESETS}
    if widget_type == "app_route":
        keys.update(preset["key"] for preset in ROUTE_HIDDEN_SECTION_PRESETS.get(app_route or "", []))
    return keys


def normalize_hidden_sections(value, widget_type, app_route):
    if value in (None, ""):
        raw_values = []
    elif isinstance(value, list | tuple | set):
        raw_values = list(value)
    else:
        raise ValidationError("Hidden sections must be a list of preset keys.")

    selected = []
    for item in raw_values:
        key = str(item or "").strip()
        if key and key not in selected:
            selected.append(key)

    allowed = allowed_hidden_section_keys(widget_type, app_route)
    invalid = [key for key in selected if key not in allowed]
    if invalid:
        raise ValidationError(f"Unknown or unavailable hidden section preset(s): {', '.join(invalid)}.")

    order = [preset["key"] for preset in all_hidden_section_presets()]
    return [key for key in order if key in selected]


def effective_hidden_sections(widget):
    selected = widget.hidden_sections if isinstance(widget.hidden_sections, list) else []
    if widget.hide_section_titles and "section_titles" not in selected:
        selected = [*selected, "section_titles"]
    try:
        return normalize_hidden_sections(selected, widget.widget_type, widget.app_route)
    except ValidationError:
        allowed = allowed_hidden_section_keys(widget.widget_type, widget.app_route)
        selected_keys = {str(key or "").strip() for key in selected}
        order = [preset["key"] for preset in all_hidden_section_presets()]
        return [key for key in order if key in selected_keys and key in allowed]
