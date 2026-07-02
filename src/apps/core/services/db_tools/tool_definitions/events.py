from .common import prop, tool_spec

DEFINITIONS = [
    tool_spec(
        "search_events",
        "Search events by name, date range, live status, or open-registration status.",
        {
            "name": prop("string", "Search by event name (partial match)"),
            "is_live": prop("boolean", "Filter by live status"),
            "registration_open": prop("boolean", "Filter by whether public registration is open"),
            "date_from": prop("string", "Start date (YYYY-MM-DD)"),
            "date_to": prop("string", "End date (YYYY-MM-DD)"),
        },
    ),
    tool_spec(
        "get_event_registrations",
        "Get registrations for an event. Can return the full list or just a count.",
        {
            "event_name": prop("string", "Filter by event name (partial match)"),
            "event_id": prop("string", "Filter by exact event UUID"),
            "count_only": prop("boolean", "If true, only return the count"),
        },
    ),
    tool_spec(
        "get_checkin_stats",
        "Get check-in statistics for events, optionally filtered by event name.",
        {
            "event_name": prop("string", "Filter by event name (partial match)"),
            "event_id": prop("string", "Filter by exact event UUID"),
        },
    ),
]
