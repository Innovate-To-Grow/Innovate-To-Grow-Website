"""
Side Effect Helper Functions

This module contains functions that handle the worksheet side effects for event
registration and user updates. These functions are separated from the pure
business logic to enable better testing, maintainability, and reusability.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from gspread.cell import Cell

from project import sh, tz, wks, get_wks_columns, get_wks_records


def execute_cell_updates(
        cell_updates: List[Dict[str, Any]], worksheet_name: str = "membership"
) -> None:
    """
    Execute a batch of cell updates on a specified worksheet.

    Args:
        cell_updates: List of dicts with keys: row, column, value
        worksheet_name: Name of worksheet to update ("membership" or event name)
    """
    if not cell_updates:
        return

    # Get the appropriate worksheet
    if worksheet_name == "membership":
        worksheet = wks
        columns = get_wks_columns(wks)
    else:
        worksheet = sh.worksheet(worksheet_name)
        columns = get_wks_columns(worksheet)

    # Convert to Cell objects
    cells = []
    for update in cell_updates:
        cell = Cell(
            row=update["row"], col=columns[update["column"]], value=update["value"]
        )
        cells.append(cell)

    # Execute batch update
    if cells:
        worksheet.update_cells(cells)


def refresh_user_data(
        primary_email: str, secondary_email: str
) -> Optional[Dict[str, Any]]:
    """
    Re-fetch user data from worksheet after updates.

    Args:
        primary_email: User's primary email
        secondary_email: User's secondary email

    Returns:
        Updated user record or None if not found
    """
    wks_records = get_wks_records(wks)

    # Find user by email combination
    for row in wks_records:
        if (
                row["Primary Email"] == primary_email
                and row["Secondary Email"] == secondary_email
        ):
            return row

    return None


def create_event_registration(
        event_worksheet_name: str, user_data: Dict[str, Any], event_data: Dict[str, Any]
) -> None:
    """
    Create a new event registration row in the event worksheet.

    Args:
        event_worksheet_name: Name of the event worksheet
        user_data: User information (name, emails, etc.)
        event_data: Event-specific data (ticket type, answers, etc.)
    """
    event_wks = sh.worksheet(event_worksheet_name)
    event_wks_columns = get_wks_columns(event_wks)

    # Create new row with all required data
    row = ["" for i in range(len(event_wks.row_values(1)))]

    # Generate order number
    last_order = event_wks.col_values(1)[-1] if event_wks.col_values(1) else "0"
    order = int(last_order) + 1 if last_order.isdigit() else 1

    # Set basic fields
    current_time = (
        datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")
    )

    row[event_wks_columns["Order"] - 1] = order
    row[event_wks_columns["First Name"] - 1] = user_data["first_name"]
    row[event_wks_columns["Last Name"] - 1] = user_data["last_name"]
    row[event_wks_columns["When Started"] - 1] = current_time
    row[event_wks_columns["Last Updated"] - 1] = current_time
    row[event_wks_columns["Membership Primary"] - 1] = user_data["primary_email"]
    row[event_wks_columns["Membership Secondary"] - 1] = user_data["secondary_email"]

    # Set event-specific fields
    for field_name, value in event_data.items():
        if field_name in event_wks_columns:
            row[event_wks_columns[field_name] - 1] = value

    # Append the new row
    event_wks.append_row(row)


def update_subscription_status(
        user_row: int,
        primary_subscription: Optional[bool],
        secondary_subscription: Optional[bool],
        primary_verified: bool,
        secondary_verified: bool,
        secondary_email: str = None,
) -> None:
    """
    Update subscription status based on verification status and user preferences.

    Args:
        user_row: Row number of the user
        primary_subscription: User's primary email subscription preference (None = keep existing)
        secondary_subscription: User's secondary email subscription preference (None = keep existing)
        primary_verified: Whether primary email is verified
        secondary_verified: Whether secondary email is verified
        secondary_email: Current secondary email (to check if it was cleared)
    """
    wks_columns = get_wks_columns(wks)
    cells = []

    # Primary subscription logic
    if primary_verified and primary_subscription is not None:
        # User preference applies only if email is verified
        cells.append(
            Cell(
                user_row,
                wks_columns["Primary Subscribed"],
                str(primary_subscription).upper(),
            )
        )
    elif not primary_verified:
        # Unverified emails cannot be subscribed
        cells.append(Cell(user_row, wks_columns["Primary Subscribed"], "FALSE"))

    # Secondary subscription logic
    # Only update secondary subscription if secondary email exists
    if secondary_email:  # Only process if secondary email is not empty
        if secondary_verified and secondary_subscription is not None:
            # User preference applies only if email is verified
            cells.append(
                Cell(
                    user_row,
                    wks_columns["Secondary Subscribed"],
                    str(secondary_subscription).upper(),
                )
            )
        elif not secondary_verified:
            # Unverified emails cannot be subscribed
            cells.append(Cell(user_row, wks_columns["Secondary Subscribed"], "FALSE"))

    # Apply updates
    if cells:
        wks.update_cells(cells)


def update_completion_status(user_row: int) -> None:
    """
    Mark user registration as completed and update timestamp.

    Args:
        user_row: Row number of the user
    """
    wks_columns = get_wks_columns(wks)
    current_time = (
        datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")
    )

    cells = [
        Cell(user_row, wks_columns["Last Updated"], current_time),
        Cell(user_row, wks_columns["Info Completed"], "TRUE"),
    ]

    wks.update_cells(cells)
