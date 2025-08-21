from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class EmailChangeDecision:
    """
    Represents the analysis of email changes for a user update.

    Attributes:
        change_type: Type of email change ("swap_complete", "swap_partial", "new_emails", "no_change")
        emails_needing_verification: List of email addresses that need verification emails sent
        verification_status_updates: Dict mapping email type to whether verification should be reset
        subscription_updates: Dict mapping email type to subscription status based on verification rules
    """
    change_type: str
    emails_needing_verification: List[str]
    verification_status_updates: Dict[str, bool]  # {"primary": False, "secondary": True}
    subscription_updates: Dict[str, bool]  # {"primary": False, "secondary": True}


def analyze_email_changes(
    current_user: Dict[str, Any],
    new_primary_email: str,
    new_secondary_email: str
) -> EmailChangeDecision:
    """
    Analyzes email changes and determines what verification actions are needed.

    This is a pure function that contains all the business logic for email changes
    without any side effects (no database updates, no email sending).

    Args:
        current_user: Current user record with existing email information
        new_primary_email: New primary email the user wants
        new_secondary_email: New secondary email the user wants

    Returns:
        EmailChangeDecision with analysis of what needs to happen
    """
    current_primary = current_user["Primary Email"]
    current_secondary = current_user["Secondary Email"]

    # Determine change type
    if current_primary == new_primary_email and current_secondary == new_secondary_email:
        change_type = "no_change"
        emails_needing_verification = []
        verification_updates = {"primary": False, "secondary": False}

    elif current_primary == new_secondary_email and current_secondary == new_primary_email:
        change_type = "swap_complete"
        emails_needing_verification = []
        # Verification status gets swapped, not reset
        verification_updates = {"primary": False, "secondary": False}

    elif current_primary == new_secondary_email:
        change_type = "swap_partial"
        emails_needing_verification = [new_primary_email]
        # Primary gets new email (needs verification), secondary keeps verification from old primary
        verification_updates = {"primary": True, "secondary": False}

    elif current_secondary == new_primary_email:
        change_type = "swap_partial"
        emails_needing_verification = [new_secondary_email]
        # Primary keeps verification from old secondary, secondary gets new email (needs verification)
        verification_updates = {"primary": False, "secondary": True}

    else:
        change_type = "new_emails"
        emails_needing_verification = []
        verification_updates = {"primary": False, "secondary": False}

        # Check which emails actually changed
        if current_primary != new_primary_email:
            emails_needing_verification.append(new_primary_email)
            verification_updates["primary"] = True

        if current_secondary != new_secondary_email:
            emails_needing_verification.append(new_secondary_email)
            verification_updates["secondary"] = True

    # Calculate subscription updates based on verification rules
    # Unverified emails must have subscription = False
    subscription_updates = {}
    for email_type in ["primary", "secondary"]:
        if verification_updates[email_type]:  # Email will need verification
            subscription_updates[email_type] = False
        else:
            # Keep existing subscription status (will be handled by caller)
            subscription_updates[email_type] = None

    return EmailChangeDecision(
        change_type=change_type,
        emails_needing_verification=emails_needing_verification,
        verification_status_updates=verification_updates,
        subscription_updates=subscription_updates
    )


def calculate_verification_cell_updates(
    current_user: Dict[str, Any],
    decision: EmailChangeDecision,
    row_number: int
) -> List[Dict[str, Any]]:
    """
    Calculates what cell updates are needed for email verification status changes.

    Pure function that determines worksheet updates without executing them.

    Args:
        current_user: Current user record
        decision: Email change decision from analyze_email_changes
        row_number: Row number in worksheet for this user

    Returns:
        List of cell update dictionaries with row, column, value
    """
    updates = []

    if decision.change_type == "swap_complete":
        # Swap all verification-related fields
        updates.extend([
            {"row": row_number, "column": "Primary Verified", "value": current_user["Secondary Verified"]},
            {"row": row_number, "column": "Secondary Verified", "value": current_user["Primary Verified"]},
            {"row": row_number, "column": "Primary Expired", "value": current_user["Secondary Expired"]},
            {"row": row_number, "column": "Secondary Expired", "value": current_user["Primary Expired"]},
            {"row": row_number, "column": "Primary Bounced", "value": current_user["Secondary Bounced"]},
            {"row": row_number, "column": "Secondary Bounced", "value": current_user["Primary Bounced"]},
        ])

    elif decision.change_type == "swap_partial":
        if decision.verification_status_updates["primary"]:
            # Primary email is new, secondary inherits from old primary
            updates.extend([
                {"row": row_number, "column": "Primary Verified", "value": "FALSE"},
                {"row": row_number, "column": "Primary Expired", "value": "FALSE"},
                {"row": row_number, "column": "Primary Bounced", "value": ""},
                {"row": row_number, "column": "Secondary Verified", "value": current_user["Primary Verified"]},
                {"row": row_number, "column": "Secondary Expired", "value": current_user["Primary Expired"]},
                {"row": row_number, "column": "Secondary Bounced", "value": current_user["Primary Bounced"]},
            ])
        else:
            # Secondary email is new, primary inherits from old secondary
            updates.extend([
                {"row": row_number, "column": "Primary Verified", "value": current_user["Secondary Verified"]},
                {"row": row_number, "column": "Primary Expired", "value": current_user["Secondary Expired"]},
                {"row": row_number, "column": "Primary Bounced", "value": current_user["Secondary Bounced"]},
                {"row": row_number, "column": "Secondary Verified", "value": "FALSE"},
                {"row": row_number, "column": "Secondary Expired", "value": "FALSE"},
                {"row": row_number, "column": "Secondary Bounced", "value": ""},
            ])

    elif decision.change_type == "new_emails":
        # Reset verification for any changed emails
        if decision.verification_status_updates["primary"]:
            updates.extend([
                {"row": row_number, "column": "Primary Verified", "value": "FALSE"},
                {"row": row_number, "column": "Primary Expired", "value": "FALSE"},
                {"row": row_number, "column": "Primary Bounced", "value": ""},
            ])
        if decision.verification_status_updates["secondary"]:
            updates.extend([
                {"row": row_number, "column": "Secondary Verified", "value": "FALSE"},
                {"row": row_number, "column": "Secondary Expired", "value": "FALSE"},
                {"row": row_number, "column": "Secondary Bounced", "value": ""},
            ])

    return updates


def calculate_basic_user_updates(
    form_data: Dict[str, Any],
    row_number: int,
    custom_fields: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Calculates basic user information updates (name, emails, custom fields).

    Pure function that determines what basic data updates are needed.

    Args:
        form_data: Form data with user's new information
        row_number: Row number in worksheet for this user
        custom_fields: List of custom field definitions (optional)

    Returns:
        List of cell update dictionaries
    """
    updates = [
        {"row": row_number, "column": "First Name", "value": form_data["first_name"]},
        {"row": row_number, "column": "Last Name", "value": form_data["last_name"]},
        {"row": row_number, "column": "Primary Email", "value": form_data["primary_email"]},
        {"row": row_number, "column": "Secondary Email", "value": form_data["secondary_email"]},
    ]

    # Add custom fields if provided
    if custom_fields:
        for field in custom_fields:
            field_name = field["label"]
            if field_name in form_data:
                if field["field_type"] == "Checkbox":
                    # Handle checkbox fields specially (convert list to newline-separated string)
                    value = "\n".join(form_data[field_name]) if form_data[field_name] else ""
                else:
                    value = form_data[field_name]
                updates.append({"row": row_number, "column": field_name, "value": value})

    return updates


def make_sure(
    can_update: bool,
    wks_records: list[dict],
    current_user_row: int,
    new_primary_email: str,
    new_secondary_email: str
):
    """
    Validates email changes for event registration updates.

    Checks if the new primary/secondary emails conflict with existing users.
    If conflicts exist with expired emails, clears them and sends notifications.
    If conflicts exist with active emails, blocks the update.

    Args:
        can_update: Initial state (should be True)
        wks_records: List of user records from worksheet
        current_user_row: Row number of the user making the update
        new_primary_email: New primary email the user wants
        new_secondary_email: New secondary email the user wants

    Returns:
        tuple: (can_update, cells_to_update, emails_to_send)
            - can_update: bool - whether the update should proceed
            - cells_to_update: list - cell updates to clear expired emails
            - emails_to_send: list - notification emails to send
    """
    cells_to_update = []
    emails_to_send = []

    # Define the validation matrix: (email_to_check, column_to_search)
    validations = [
        (new_primary_email, "Primary Email"),
        (new_primary_email, "Secondary Email"),
        (new_secondary_email, "Primary Email"),
        (new_secondary_email, "Secondary Email")
    ]

    for email_to_check, column_to_search in validations:
        # Find existing user with this email in this column
        matching_users = [row for row in wks_records if row[column_to_search] == email_to_check]

        if not matching_users:
            continue  # No conflict, move to next validation

        existing_user = matching_users[0]  # Take first match
        existing_user_row = existing_user["Row"]

        # Skip if this is the same user (no conflict with yourself)
        if existing_user_row == current_user_row:
            continue

        # Determine the verification status field based on column
        if column_to_search == "Primary Email":
            expired_field = "Primary Expired"
            verified_field = "Primary Verified"
            other_email_field = "Secondary Email"
            other_verified_field = "Secondary Verified"
            email_being_cleared = existing_user["Primary Email"]
        else:  # Secondary Email
            expired_field = "Secondary Expired"
            verified_field = "Secondary Verified"
            other_email_field = "Primary Email"
            other_verified_field = "Primary Verified"
            email_being_cleared = existing_user["Secondary Email"]

        # Check if the conflicting email is expired
        if existing_user[expired_field] == "FALSE":
            # Email is still active - block the update
            can_update = False

        elif existing_user[expired_field] == "TRUE":
            # Email is expired - we can claim it
            # Add cell update to clear the expired email
            cells_to_update.append({
                "row": existing_user_row,
                "column": column_to_search,
                "value": ""  # Clear the email
            })

            # Send notification email if the user has another verified email
            other_email = existing_user[other_email_field]
            if other_email != "" and existing_user[other_verified_field] == "TRUE":
                emails_to_send.append({
                    "to": other_email,
                    "type": "deletion_notice",
                    "user_first_name": existing_user["First Name"],
                    "user_last_name": existing_user["Last Name"],
                    "deleted_email": email_being_cleared
                })

    return can_update, cells_to_update, emails_to_send
