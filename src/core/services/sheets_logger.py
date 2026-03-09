"""
Async audit-logging service — writes rows to the Logs worksheet in Google Sheets.

Every log call fires in a background daemon thread so it never blocks a
Django request/response cycle. Exceptions from the background thread are caught
and emitted to the Django logger (never re-raised to the caller).

Logs worksheet column structure (matches the old Flask system exactly):
    Order | Transaction | DateTime | [additional fields...]

Usage:
    from core.services import sheets_logger

    sheets_logger.log_email_submission("/about", "user@example.com")
    sheets_logger.log_registration("/membership/register", "Jane", "Doe", "j@example.com", "")
"""

import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from . import google_sheets as sheets

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Los_Angeles")
_LOGS_WORKSHEET = "Logs"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    """Return the current Pacific time as a formatted string, matching the old Flask format."""
    return datetime.now(_TZ).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")


def _next_order() -> int:
    """
    Determine the next Order number by reading the last value in column 1 (Order).

    Column 1 contains: ["Order", "1", "2", ...]. We skip the header and return
    last_digit + 1, or 1 if the sheet is empty. Mirrors the old Flask pattern:
        int(logs.col_values(1)[-1]) + 1 if isdigit() else 1
    """
    all_values = sheets.get_column_values(_LOGS_WORKSHEET, col=1)
    data_values = all_values[1:]  # skip "Order" header
    for val in reversed(data_values):
        if val.isdigit():
            return int(val) + 1
    return 1


def _fire(extra_fields: list) -> None:
    """
    Append a log row in a background daemon thread.

    The row format is: [Order, Transaction, DateTime, *extra_fields]
    where Transaction and DateTime are the first two items of extra_fields.
    Errors are logged to Django's logger and never propagated.
    """

    def _append():
        try:
            order = _next_order()
            sheets.append_row(_LOGS_WORKSHEET, [order, *extra_fields])
        except Exception:
            logger.exception("sheets_logger: failed to write log row to Sheets")

    thread = threading.Thread(target=_append, daemon=True)
    thread.start()


# ---------------------------------------------------------------------------
# Public API — mirrors the old Flask Logger class methods exactly
# ---------------------------------------------------------------------------


def log_email_submission(path: str, email: str) -> None:
    """Log an email form submission (e.g. newsletter signup entry point)."""
    _fire([path, _now(), f"Email: {email}"])


def log_registration(
    path: str,
    first_name: str,
    last_name: str,
    primary_email: str,
    secondary_email: str,
) -> None:
    """Log the initial registration step."""
    _fire([
        path,
        _now(),
        f"First Name: {first_name}",
        f"Last Name: {last_name}",
        f"Primary Email: {primary_email}",
        f"Secondary Email: {secondary_email}",
    ])


def log_update(
    path: str,
    first_name: str,
    last_name: str,
    primary_email: str,
    secondary_email: str,
) -> None:
    """Log a member profile update."""
    _fire([
        path,
        _now(),
        f"First Name: {first_name}",
        f"Last Name: {last_name}",
        f"Primary Email: {primary_email}",
        f"Secondary Email: {secondary_email}",
    ])


def log_event_register(
    path: str,
    first_name: str,
    last_name: str,
    primary_email: str,
    secondary_email: str,
) -> None:
    """Log an event registration."""
    _fire([
        path,
        _now(),
        f"First Name: {first_name}",
        f"Last Name: {last_name}",
        f"Primary Email: {primary_email}",
        f"Secondary Email: {secondary_email}",
    ])


def log_complete_registration(
    path: str,
    first_name: str,
    last_name: str,
    primary_email: str,
    secondary_email: str,
    phone_number: str = "",
    register_event: str = "No Event",
) -> None:
    """Log the completion of a member profile (info form submitted)."""
    phone_info = f"Phone: {phone_number}" if phone_number else "No Phone"
    _fire([
        path,
        _now(),
        f"First Name: {first_name}",
        f"Last Name: {last_name}",
        f"Primary Email: {primary_email}",
        f"Secondary Email: {secondary_email}",
        phone_info,
        register_event,
    ])


def log_background_error(route: str, user_email: str, error_details: dict) -> None:
    """
    Log a background thread error with full diagnostic detail.

    error_details keys: error_type, error_message, stack_trace
    """
    stack_trace = error_details.get("stack_trace", "No stack trace available")
    _fire([
        route,
        _now(),
        "BACKGROUND_ERROR",
        f"User: {user_email}",
        error_details.get("error_type", "Unknown"),
        error_details.get("error_message", "No message"),
        stack_trace,
    ])
