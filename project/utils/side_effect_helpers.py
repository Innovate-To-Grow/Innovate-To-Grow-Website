"""
Side Effect Helper Functions

This module contains functions that handle all the side effects for event registration
and user updates. These functions are separated from the pure business logic to enable
better testing, maintainability, and reusability.

Functions in this module:
- Execute database/worksheet updates
- Send emails (verification, confirmation, notification)
- Start background timers
- Handle Flask context operations
"""

import time
from datetime import datetime
from threading import Thread
from typing import List, Dict, Any, Optional

from flask import url_for, render_template, copy_current_request_context
from gspread.cell import Cell

from project import app, sh, wks, tz, get_wks_records, get_wks_columns
from project.utils.email import send_email
from project.utils.token import generate_token


def execute_cell_updates(
    cell_updates: List[Dict[str, Any]],
    worksheet_name: str = "membership"
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
            row=update["row"],
            col=columns[update["column"]],
            value=update["value"]
        )
        cells.append(cell)

    # Execute batch update
    if cells:
        worksheet.update_cells(cells)


def send_verification_email(
    email: str,
    user_first_name: str,
    user_last_name: str,
    start_expiry_timer: bool = True
) -> None:
    """
    Send a verification email to the specified address.

    Args:
        email: Email address to send verification to
        user_first_name: User's first name for personalization
        user_last_name: User's last name for personalization
        start_expiry_timer: Whether to start the expiry timer for this email
    """
    token = generate_token(email)
    confirm_url = url_for("registration.confirm", token=token, _external=True)

    html = render_template(
        "verify_email.html",
        first=user_first_name,
        last=user_last_name,
        confirm_url=confirm_url,
    )

    send_email(email, app.config["VERIF_SUBJECT"], html)

    if start_expiry_timer:
        start_email_expiry_timer(email)


def send_confirmation_email(
    email: str,
    subject: str,
    template_name: str,
    template_data: Dict[str, Any]
) -> None:
    """
    Send a confirmation/receipt email using specified template.

    Args:
        email: Recipient email address
        subject: Email subject line
        template_name: Name of the template to render
        template_data: Data to pass to the template
    """
    html = render_template(template_name, **template_data)
    send_email(email, subject, html)


def send_deletion_notice_email(
    email: str,
    user_first_name: str,
    user_last_name: str,
    deleted_email: str
) -> None:
    """
    Send notification that an email address has been removed from their account.

    Args:
        email: Email to send notification to (their other verified email)
        user_first_name: User's first name
        user_last_name: User's last name
        deleted_email: The email address that was removed
    """
    html = render_template(
        "deleting_email.html",
        first=user_first_name,
        last=user_last_name,
        email=deleted_email
    )
    send_email(email, app.config["REMOVE_SUBJECT"], html)


def start_email_expiry_timer(email: str) -> None:
    """
    Start a background timer to mark email as expired if not verified.

    Args:
        email: Email address to set expiry timer for
    """
    @copy_current_request_context
    def expiry_timer():
        time.sleep(app.config["EXPIRY_TIMER"])

        # Re-fetch current data to check verification status
        wks_records = get_wks_records(wks)
        wks_columns = get_wks_columns(wks)

        # Find user with this email (could be primary or secondary)
        user_row = None
        email_type = None

        for row in wks_records:
            if row["Primary Email"] == email:
                user_row = row
                email_type = "Primary"
                break
            elif row["Secondary Email"] == email:
                user_row = row
                email_type = "Secondary"
                break

        if user_row and user_row[f"{email_type} Verified"] == "FALSE":
            # Email is still unverified, mark as expired
            wks.update_cell(
                user_row["Row"],
                wks_columns[f"{email_type} Expired"],
                "TRUE"
            )

    thread = Thread(target=expiry_timer)
    thread.start()


def refresh_user_data(primary_email: str, secondary_email: str) -> Optional[Dict[str, Any]]:
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
        if (row["Primary Email"] == primary_email and
            row["Secondary Email"] == secondary_email):
            return row

    return None


def create_event_registration(
    event_worksheet_name: str,
    user_data: Dict[str, Any],
    event_data: Dict[str, Any]
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
    current_time = datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")

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
    secondary_verified: bool
) -> None:
    """
    Update subscription status based on verification status and user preferences.

    Args:
        user_row: Row number of the user
        primary_subscription: User's primary email subscription preference (None = keep existing)
        secondary_subscription: User's secondary email subscription preference (None = keep existing)
        primary_verified: Whether primary email is verified
        secondary_verified: Whether secondary email is verified
    """
    wks_columns = get_wks_columns(wks)
    cells = []

    # Primary subscription logic
    if primary_verified and primary_subscription is not None:
        # User preference applies only if email is verified
        cells.append(Cell(user_row, wks_columns["Primary Subscribed"], str(primary_subscription).upper()))
    elif not primary_verified:
        # Unverified emails cannot be subscribed
        cells.append(Cell(user_row, wks_columns["Primary Subscribed"], "FALSE"))

    # Secondary subscription logic
    if secondary_verified and secondary_subscription is not None:
        # User preference applies only if email is verified
        cells.append(Cell(user_row, wks_columns["Secondary Subscribed"], str(secondary_subscription).upper()))
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
    current_time = datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")

    cells = [
        Cell(user_row, wks_columns["Last Updated"], current_time),
        Cell(user_row, wks_columns["Info Completed"], "TRUE")
    ]

    wks.update_cells(cells)


def send_event_confirmation_emails(
    user: Dict[str, Any],
    event_name: str,
    event_url: str,
    update_url: str,
    info_fields: Dict[str, Any],
    event_fields: Dict[str, Any]
) -> None:
    """
    Send event registration confirmation emails to verified addresses.

    Args:
        user: User data with verification status
        event_name: Name of the event
        event_url: URL to event registration
        update_url: URL to update registration
        info_fields: User's profile information
        event_fields: Event-specific registration data
    """
    subject = f"{event_name} Registration Completed"

    template_data = {
        "event_url": event_url,
        "update_url": update_url,
        "first": user["First Name"],
        "last": user["Last Name"],
        "primary_email": user["Primary Email"],
        "primary_verified": user["Primary Verified"],
        "primary_subscribed": user["Primary Subscribed"],
        "secondary_email": user["Secondary Email"],
        "secondary_verified": user["Secondary Verified"],
        "secondary_subscribed": user["Secondary Subscribed"],
        "info_fields": info_fields,
        "event_name": event_name,
        "event_fields": event_fields
    }

    # Send to verified emails only
    if user["Primary Verified"] == "TRUE":
        send_confirmation_email(
            user["Primary Email"],
            subject,
            "event_receipt_email.html",
            template_data
        )

    if user["Secondary Verified"] == "TRUE":
        send_confirmation_email(
            user["Secondary Email"],
            subject,
            "event_receipt_email.html",
            template_data
        )
