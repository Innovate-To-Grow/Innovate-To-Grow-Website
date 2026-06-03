"""
General Utility Functions

Common utility functions used across the application for data processing,
form handling, and user queries.
"""

from typing import List, Dict, Any


async def query_primary_column(
        email: str, wks_records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Query worksheet records to find users by primary email.

    This function searches for users whose primary email matches the given email address.
    It returns the results in a format that matches the original async query pattern
    used in the registration system.

    Args:
        email: Email address to search for
        wks_records: List of worksheet records to search through

    Returns:
        List of matching user records (the calling code expects user[0] to be a dict)
    """
    # Convert email to lowercase for case-insensitive comparison
    email_lower = email.lower()

    # Find all users with matching primary email
    matching_users = [
        row
        for row in wks_records
        if row.get("Primary Email", "").lower() == email_lower
    ]

    # Return the list of matching users directly
    # The calling code does: user = result, then user[0] to get first match
    return matching_users


def extract_from_form(form):
    """
    Extract common form fields from a form object.

    Args:
        form: WTForms form object

    Returns:
        Tuple of (first_name, last_name, primary_email, secondary_email, phone_number)
    """
    first_name = form.first_name.data if hasattr(form, "first_name") else ""
    last_name = form.last_name.data if hasattr(form, "last_name") else ""
    primary_email = form.primary_email.data if hasattr(form, "primary_email") else ""
    secondary_email = (
        form.secondary_email.data if hasattr(form, "secondary_email") else ""
    )

    # Construct phone number if available
    phone_number = ""
    if hasattr(form, "country_code") and hasattr(form, "phone_number"):
        if form.country_code.data and form.phone_number.data:
            phone_number = form.country_code.data + form.phone_number.data

    return first_name, last_name, primary_email, secondary_email, phone_number


def log(
        logs,
        route: str,
        primary_email: str,
        first_name: str = "",
        last_name: str = "",
        secondary_email: str = "",
        phone_number: str = "",
        additional_info: str = "",
):
    """
    Log user action to the logs worksheet.

    Args:
        logs: Logs worksheet object
        route: Route that was accessed
        primary_email: User's primary email
        first_name: User's first name (optional)
        last_name: User's last name (optional)
        secondary_email: User's secondary email (optional)
        phone_number: User's phone number (optional)
        additional_info: Any additional information to log (optional)
    """
    from datetime import datetime
    from project import tz

    order = int(logs.col_values(1)[-1]) + 1 if logs.col_values(1)[-1].isdigit() else 1

    # Build log entry
    log_entry = [
        order,
        route,
        str(
            datetime.now(tz)
            .replace(second=0, microsecond=0)
            .strftime("%Y-%m-%d %I:%M %p")
        ),
        f"Primary Email: {primary_email}",
    ]

    # Add optional fields if provided
    if first_name:
        log_entry.append(f"First Name: {first_name}")
    if last_name:
        log_entry.append(f"Last Name: {last_name}")
    if secondary_email:
        log_entry.append(f"Secondary Email: {secondary_email}")
    if phone_number:
        log_entry.append(f"Phone: {phone_number}")
    if additional_info:
        log_entry.append(additional_info)

    logs.append_row(log_entry)


def find_user_by_email(
        email: str, wks_records: List[Dict[str, Any]], search_both_columns: bool = True
) -> Dict[str, Any]:
    """
    Find a user by email address in worksheet records.

    Args:
        email: Email address to search for
        wks_records: List of worksheet records
        search_both_columns: Whether to search both primary and secondary email columns

    Returns:
        User record if found, None otherwise
    """
    email_lower = email.lower()

    # Search primary email column
    for record in wks_records:
        if record.get("Primary Email", "").lower() == email_lower:
            return record

    # Search secondary email column if requested
    if search_both_columns:
        for record in wks_records:
            if record.get("Secondary Email", "").lower() == email_lower:
                return record

    return None


def validate_email_format(email: str) -> bool:
    """
    Basic email format validation.

    Args:
        email: Email address to validate

    Returns:
        Boolean indicating if email format is valid
    """
    import re

    if not email or not isinstance(email, str):
        return False

    # Basic email regex pattern
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email.strip()) is not None


def clean_phone_number(phone_number: str) -> str:
    """
    Clean and format phone number by removing non-digit characters.

    Args:
        phone_number: Raw phone number string

    Returns:
        Cleaned phone number with only digits
    """
    import re

    if not phone_number:
        return ""

    # Remove all non-digit characters except + at the beginning
    if phone_number.startswith("+"):
        return "+" + re.sub(r"[^\d]", "", phone_number[1:])
    else:
        return re.sub(r"[^\d]", "", phone_number)
