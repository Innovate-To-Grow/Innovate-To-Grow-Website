from datetime import date


def format_event_date_range(start_date: date, end_date: date) -> str:
    """Format an inclusive all-day event range without repeating unnecessary parts."""
    if end_date < start_date:
        raise ValueError("Event end date cannot be earlier than its start date.")

    if start_date == end_date:
        return f"{start_date:%B} {start_date.day}, {start_date.year}"

    if start_date.year != end_date.year:
        return f"{start_date:%B} {start_date.day}, {start_date.year}–{end_date:%B} {end_date.day}, {end_date.year}"

    if start_date.month != end_date.month:
        return f"{start_date:%B} {start_date.day}–{end_date:%B} {end_date.day}, {end_date.year}"

    return f"{start_date:%B} {start_date.day}–{end_date.day}, {end_date.year}"
