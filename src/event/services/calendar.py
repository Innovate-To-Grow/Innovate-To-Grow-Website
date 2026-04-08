"""
Calendar utilities for event ticket emails.

Generates .ics calendar files and Google Calendar URLs for all-day events.
"""

import datetime
from urllib.parse import quote, urlencode


def generate_ics(*, event_uid, event_name, event_date, event_location, event_description=""):
    """Generate an ICS calendar string for an all-day event."""
    date_str = event_date.strftime("%Y%m%d")
    next_day = (event_date + datetime.timedelta(days=1)).strftime("%Y%m%d")
    now = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Innovate to Grow//Ticket//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event_uid}@i2g.ucmerced.edu",
        f"DTSTAMP:{now}",
        f"DTSTART;VALUE=DATE:{date_str}",
        f"DTEND;VALUE=DATE:{next_day}",
        f"SUMMARY:{_ics_escape(event_name)}",
        f"LOCATION:{_ics_escape(event_location)}",
    ]
    if event_description:
        lines.append(f"DESCRIPTION:{_ics_escape(event_description)}")
    lines += [
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


def build_google_calendar_url(*, event_name, event_date, event_location, event_description=""):
    """Build a Google Calendar 'Add Event' URL for an all-day event."""
    date_str = event_date.strftime("%Y%m%d")
    next_day = (event_date + datetime.timedelta(days=1)).strftime("%Y%m%d")

    params = urlencode(
        {
            "action": "TEMPLATE",
            "text": event_name,
            "dates": f"{date_str}/{next_day}",
            "location": event_location,
            "details": event_description or "",
        },
        quote_via=quote,
    )
    return f"https://calendar.google.com/calendar/render?{params}"


def _ics_escape(text):
    """Escape special characters for ICS format."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
