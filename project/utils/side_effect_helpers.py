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


def send_verification_email(
    email: str,
    user_first_name: str,
    user_last_name: str,
    start_expiry_timer: bool = True,
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
    email: str, subject: str, template_name: str, template_data: Dict[str, Any]
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
    email: str, user_first_name: str, user_last_name: str, deleted_email: str
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
        email=deleted_email,
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
                user_row["Row"], wks_columns[f"{email_type} Expired"], "TRUE"
            )

    thread = Thread(target=expiry_timer)
    thread.start()


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


def send_event_confirmation_emails(
    user: Dict[str, Any],
    event_name: str,
    event_url: str,
    update_url: str,
    info_fields: Dict[str, Any],
    event_fields: Dict[str, Any],
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

    # Format phone number with + prefix for display
    phone_num = user.get("Phone Number", "")
    if phone_num:
        phone_num_str = str(phone_num)
        phone_display = (
            f"+{phone_num_str}" if not phone_num_str.startswith("+") else phone_num_str
        )
    else:
        phone_display = ""

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
        "phone_number": phone_display,
        "phone_number_verified": user.get("Phone number verified", "FALSE"),
        "phone_subscribed": user.get("Phone number subscribed", "FALSE"),
        "info_fields": info_fields,
        "event_name": event_name,
        "event_fields": event_fields,
    }

    # Send to verified emails only
    if user["Primary Verified"] == "TRUE" and user["Primary Email"]:
        send_confirmation_email(
            user["Primary Email"], subject, "event_receipt_email.html", template_data
        )

    if user["Secondary Verified"] == "TRUE" and user["Secondary Email"]:
        send_confirmation_email(
            user["Secondary Email"], subject, "event_receipt_email.html", template_data
        )


def create_complete_user_registration(
    user_data: Dict[str, Any], custom_fields: List[Dict[str, Any]] = None
) -> int:
    """
    Create a new user record for complete registration and return the row number.

    This function creates a complete user registration where:
    - Primary email is immediately verified and subscribed
    - Secondary email is unverified and unsubscribed
    - Info is marked as completed immediately
    - All custom fields are populated from user_data

    Args:
        user_data: Dictionary with all user data mapped to column names
        custom_fields: List of custom field definitions (optional, for validation)

    Returns:
        int: Row number of the created user record
    """
    wks_columns = get_wks_columns(wks)

    # Create new row array with correct length
    user_row = ["" for _ in range(len(wks.row_values(1)))]

    # Map user_data to correct column positions
    for column_name, value in user_data.items():
        if column_name in wks_columns:
            user_row[wks_columns[column_name] - 1] = value

    # Append the new user row
    wks.append_row(user_row)

    # Get the row number of the newly created user
    # The new row will be at the end, so get current row count
    new_row_number = len(wks.get_all_values())

    return new_row_number


def send_complete_registration_confirmation_email(
    primary_email: str,
    user_data: Dict[str, Any],
    info_fields: Dict[str, Any],
    event_fields: Dict[str, Any],
    event_url: Optional[str],
    update_url: str,
    event_name: Optional[str] = None,
) -> None:
    """
    Send confirmation email for complete registration.

    This function sends the confirmation email specifically for complete registration,
    which includes both membership and optional event registration information.

    Args:
        primary_email: Email address to send confirmation to (primary email)
        user_data: Complete user data including verification status
        info_fields: User's profile information fields
        event_fields: Event-specific registration data (if applicable)
        event_url: URL to event registration page (if applicable)
        update_url: URL to update user information
        event_name: Name of the event (if applicable)
    """
    subject = "I2G Membership Completed"

    template_data = {
        "event_url": event_url,
        "update_url": update_url,
        "first": user_data.get("First Name", ""),
        "last": user_data.get("Last Name", ""),
        "primary_email": user_data.get("Primary Email", ""),
        "primary_verified": user_data.get("Primary Verified", "FALSE"),
        "primary_subscribed": user_data.get("Primary Subscribed", "FALSE"),
        "secondary_email": user_data.get("Secondary Email", ""),
        "secondary_verified": user_data.get("Secondary Verified", "FALSE"),
        "secondary_subscribed": user_data.get("Secondary Subscribed", "FALSE"),
        "phone_number": str(user_data.get("Phone Number", "")),
        "phone_number_verified": user_data.get("Phone number verified", "FALSE"),
        "phone_subscribed": user_data.get("Phone number subscribed", "FALSE"),
        "info_fields": info_fields,
        "event_name": event_name,
        "event_fields": event_fields,
    }

    # Send confirmation email using the complete registration template
    send_confirmation_email(
        primary_email, subject, "info_receipt_email.html", template_data
    )


def start_phone_verification_process(phone_number: str) -> str:
    """
    Starts the Twilio OTP verification process for a phone number.
    First validates that the phone number exists using Twilio Lookup API.

    Args:
        phone_number: Full international phone number (e.g., "+15551234567")

    Returns:
        Verification status from Twilio

    Raises:
        ValueError: If phone number is invalid or doesn't exist
    """
    from project.utils.twilio import (
        client,
        verify_sid,
        start_verification_process,
        validate_phone_number_exists,
    )

    if not phone_number or phone_number.strip() == "":
        raise ValueError("Phone number is required for verification")

    # First, validate that the phone number actually exists
    validation_result = validate_phone_number_exists(phone_number)

    if not validation_result["valid"]:
        error_msg = validation_result.get("error", "Invalid phone number")
        raise ValueError(f"Phone number validation failed: {error_msg}")

    # Use the validated E.164 formatted number from Twilio
    validated_phone = validation_result["phone_number"]

    try:
        status = start_verification_process(client, validated_phone, verify_sid)
        return status
    except Exception as e:
        # Log the error but don't crash the registration
        print(f"Error starting phone verification: {e}")
        raise


def setup_otp_verification_session(
    session: Any,
    user_data: Dict[str, Any],
    event_data: Optional[Dict[str, Any]] = None,
    phone_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Sets up Flask session data for OTP verification flow.

    Args:
        session: Flask session object
        user_data: User registration data
        event_data: Event registration data (optional)
        phone_data: Phone-specific data (optional)
    """
    # Clear any existing session data for OTP
    otp_keys = [
        "phone_number",
        "first",
        "last",
        "primary_email",
        "primary_verified",
        "primary_subscribed",
        "secondary_email",
        "secondary_verified",
        "secondary_subscribed",
        "phone_subscribe",
        "info_fields",
        "update",
        "update_url",
        "event_url",
        "event_fields",
        "event_reg",
        "event_name",
    ]

    for key in otp_keys:
        session.pop(key, None)

    # Set up session data for OTP verification
    session.update(
        {
            "phone_number": phone_data.get("phone_number", "") if phone_data else "",
            "first": user_data.get("first_name", ""),
            "last": user_data.get("last_name", ""),
            "primary_email": user_data.get("primary_email", ""),
            "primary_verified": user_data.get("primary_verified", "TRUE"),
            "primary_subscribed": user_data.get("primary_subscribed", "TRUE"),
            "secondary_email": user_data.get("secondary_email", ""),
            "secondary_verified": user_data.get("secondary_verified", "FALSE"),
            "secondary_subscribed": user_data.get("secondary_subscribed", "FALSE"),
            "phone_subscribe": phone_data.get("phone_subscribe", "FALSE")
            if phone_data
            else "FALSE",
            "info_fields": user_data.get("info_fields", {}),
            "update": "FALSE",  # This is a new registration, not an update
            "update_url": user_data.get("update_url", ""),
            "event_url": event_data.get("event_url", "") if event_data else "",
            "event_fields": event_data.get("event_fields", {}) if event_data else {},
            "event_reg": event_data.get("event_reg", "no") if event_data else "no",
            "event_name": event_data.get("event_name", None) if event_data else None,
        }
    )


def send_phone_confirmation_sms(
    phone_number: str, event_name: str, phone_subscribed: bool = True
) -> None:
    """
    Sends a confirmation SMS message after successful registration.

    Args:
        phone_number: Full international phone number
        event_name: Name of the event the user registered for
        phone_subscribed: Whether the user is subscribed to SMS notifications
    """
    if not phone_subscribed or not phone_number:
        return

    from project.utils.twilio import client, send_message

    try:
        message_body = f"You have signed up for {event_name}"
        send_message(message_body, phone_number, client)
    except Exception as e:
        # Log the error but don't crash the registration
        print(f"Error sending confirmation SMS: {e}")


def update_phone_verification_status(phone_number: str, verified: bool = True) -> None:
    """
    Updates the phone verification status in the membership worksheet.

    Args:
        phone_number: Full international phone number to update
        verified: Whether the phone is now verified (default: True)
    """
    from project import wks, get_wks_records, get_wks_columns
    from project.utils.registration_utils import analyze_user_existence_check
    from datetime import datetime
    from project import tz
    from gspread.cell import Cell

    # Find the user with this phone number
    wks_records = get_wks_records(wks)
    wks_columns = get_wks_columns(wks)

    matching_users = [
        row
        for row in wks_records
        if row.get("Phone Number", "").strip() == phone_number.strip()
    ]

    if not matching_users:
        print(f"Warning: No user found with phone number {phone_number}")
        return

    user = matching_users[0]
    row_number = user["Row"]

    # Prepare cell updates
    cells = []
    cells.append(
        Cell(
            row_number,
            wks_columns["Phone number verified"],
            "TRUE" if verified else "FALSE",
        )
    )
    cells.append(
        Cell(
            row_number,
            wks_columns["Last Updated"],
            str(
                datetime.now(tz)
                .replace(second=0, microsecond=0)
                .strftime("%Y-%m-%d %I:%M %p")
            ),
        )
    )

    # Execute the update
    if cells:
        wks.update_cells(cells)


def setup_event_phone_verification_session(
    session: Any,
    user_data: Dict[str, Any],
    event_data: Dict[str, Any],
    phone_data: Dict[str, Any],
) -> None:
    """
    Sets up Flask session data for phone verification flow.

    This handles phone verification for both event registration and update flows.
    The correct template is rendered after OTP based on event_data.update_type.

    Args:
        session: Flask session object
        user_data: User information data
        event_data: Event/update context data (includes update_type for flow detection)
        phone_data: Phone-specific data
    """
    # Clear any existing session data for OTP
    otp_keys = [
        "phone_number",
        "first",
        "last",
        "primary_email",
        "primary_verified",
        "primary_subscribed",
        "secondary_email",
        "secondary_verified",
        "secondary_subscribed",
        "phone_subscribe",
        "info_fields",
        "update",
        "update_url",
        "event_url",
        "event_fields",
        "event_reg",
        "event_name",
    ]

    for key in otp_keys:
        session.pop(key, None)

    # Set up session data for event phone verification
    session.update(
        {
            "phone_number": phone_data.get("full_phone_number", ""),
            "first": user_data.get("first_name", ""),
            "last": user_data.get("last_name", ""),
            "primary_email": user_data.get("primary_email", ""),
            "primary_verified": user_data.get("primary_verified", "TRUE"),
            "primary_subscribed": user_data.get("primary_subscribed", "TRUE"),
            "secondary_email": user_data.get("secondary_email", ""),
            "secondary_verified": user_data.get("secondary_verified", "TRUE"),
            "secondary_subscribed": user_data.get("secondary_subscribed", "TRUE"),
            "phone_subscribe": "TRUE"
            if phone_data.get("phone_subscribe", False)
            else "FALSE",
            "info_fields": user_data.get("info_fields", {}),
            "update": "TRUE" if event_data.get("update_type") == "update" else "FALSE",
            "update_url": event_data.get("update_url", ""),
            "event_url": event_data.get("event_url", ""),
            "event_fields": event_data.get("event_fields", {}),
            "event_reg": "yes",  # User is registering for event
            "event_name": event_data.get("event_name", None),
        }
    )


def start_event_phone_verification_process(phone_number: str) -> str:
    """
    Starts Twilio OTP verification specifically for event registration.

    This is a wrapper around the general phone verification that includes
    event-specific error handling and logging.

    Args:
        phone_number: Full international phone number (e.g., "+15551234567")

    Returns:
        Verification status from Twilio
    """
    try:
        return start_phone_verification_process(phone_number)
    except Exception as e:
        # Log the error with event context
        print(f"Error starting event phone verification for {phone_number}: {e}")
        raise


def send_event_sms_confirmation(phone_number: str, event_name: str) -> None:
    """
    Sends SMS confirmation for event registration (no OTP needed).

    This is used when the user's phone is already verified and they're
    registering for an event.

    Args:
        phone_number: Full international phone number
        event_name: Name of the event
    """
    if not phone_number or not event_name:
        return

    try:
        send_phone_confirmation_sms(phone_number, event_name, phone_subscribed=True)
    except Exception as e:
        # Log the error but don't crash the registration
        print(f"Error sending event SMS confirmation: {e}")


def extract_phone_data_from_event_form(form) -> Dict[str, Any]:
    """
    Extract and structure phone data from event registration form.

    This is a side effect function that safely extracts phone data from
    the event form object and formats it for processing.

    Args:
        form: Event registration form object

    Returns:
        Dict with structured phone data
    """
    try:
        country_code = (
            getattr(form, "country_code", None).data
            if hasattr(form, "country_code")
            else ""
        )
        phone_number = (
            getattr(form, "phone_number", None).data
            if hasattr(form, "phone_number")
            else ""
        )
        phone_subscribe = (
            getattr(form, "phone_subscribe", None).data
            if hasattr(form, "phone_subscribe")
            else False
        )

        # Clean and format the data
        country_code = country_code.strip() if country_code else ""
        phone_number = phone_number.strip() if phone_number else ""

        full_phone = (
            country_code + phone_number if country_code and phone_number else ""
        )

        return {
            "country_code": country_code,
            "phone_number": phone_number,
            "phone_subscribe": phone_subscribe,
            "full_phone_number": full_phone,
        }
    except Exception as e:
        # Log error and return safe defaults
        print(f"Error extracting phone data from form: {e}")
        return {
            "country_code": "",
            "phone_number": "",
            "phone_subscribe": False,
            "full_phone_number": "",
        }


def create_event_registration_with_phone(
    event_worksheet_name: str,
    user_data: dict[str, Any],
    event_data: dict[str, Any],
    phone_data: Optional[dict[str, Any]] = None,
) -> None:
    """
    Create a new event registration row with phone information.

    Enhanced version of create_event_registration that includes phone data.

    Args:
        event_worksheet_name: Name of the event worksheet
        user_data: User information (name, emails, etc.)
        event_data: Event-specific data (ticket type, answers, etc.)
        phone_data: Phone-related data (optional)
    """
    try:
        event_wks = sh.worksheet(event_worksheet_name)
        event_wks_columns = get_wks_columns(event_wks)

        # Create new row with all required data
        row = ["" for i in range(len(event_wks.row_values(1)))]

        # Generate order number
        last_order = event_wks.col_values(1)[-1] if event_wks.col_values(1) else "0"
        order = int(last_order) + 1 if last_order.isdigit() else 1

        # Set basic fields
        current_time = (
            datetime.now(tz)
            .replace(second=0, microsecond=0)
            .strftime("%Y-%m-%d %I:%M %p")
        )

        row[event_wks_columns["Order"] - 1] = order
        row[event_wks_columns["First Name"] - 1] = user_data["first_name"]
        row[event_wks_columns["Last Name"] - 1] = user_data["last_name"]
        row[event_wks_columns["When Started"] - 1] = current_time
        row[event_wks_columns["Last Updated"] - 1] = current_time
        row[event_wks_columns["Membership Primary"] - 1] = user_data["primary_email"]
        row[event_wks_columns["Membership Secondary"] - 1] = user_data[
            "secondary_email"
        ]

        # Add phone data if provided and column exists
        if phone_data and "Phone Number" in event_wks_columns:
            row[event_wks_columns["Phone Number"] - 1] = phone_data.get(
                "full_phone_number", ""
            )

        # Set event-specific fields
        for field_name, value in event_data.items():
            if field_name in event_wks_columns:
                row[event_wks_columns[field_name] - 1] = value

        # Append the new row
        event_wks.append_row(row)
    except Exception as e:
        import traceback

        traceback.print_exc()
