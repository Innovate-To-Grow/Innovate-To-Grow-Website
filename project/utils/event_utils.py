from dataclasses import dataclass
from typing import List, Dict, Any, Optional


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


@dataclass
class PhoneChangeDecision:
    """
    Represents the analysis of phone number changes for a user update.

    Attributes:
        verify: Whether phone verification (OTP) is needed
        clear: Whether phone data should be cleared
        error: Whether there's a conflict with existing phone numbers
        changed: Whether the phone number was modified from current
        needs_formatting: Whether the phone number needs formatting
    """
    verify: bool = False
    clear: bool = False
    error: bool = False
    changed: bool = False
    needs_formatting: bool = False


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
            if new_primary_email:  # Only add non-empty emails for verification
                emails_needing_verification.append(new_primary_email)
            verification_updates["primary"] = True

        if current_secondary != new_secondary_email:
            if new_secondary_email:  # Only add non-empty emails for verification
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
    row_number: int,
    new_primary_email: str = None,
    new_secondary_email: str = None
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
            # Don't set secondary verification fields if secondary email is being cleared
            if new_secondary_email:  # Only set if secondary email is not empty
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

    # If secondary email is being cleared, also clear all secondary email related fields
    if not form_data["secondary_email"]:  # Empty string means clearing secondary email
        secondary_fields = [
            "Secondary Verified",
            "Secondary Subscribed",
            "Secondary Expired",
            "Secondary Bounced"
        ]
        for field in secondary_fields:
            updates.append({"row": row_number, "column": field, "value": ""})


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


def analyze_phone_number_changes(
    current_phone: Optional[str],
    new_country_code: Optional[str],
    new_phone_number: Optional[str],
    wks_records: List[Dict[str, Any]],
    current_user_row: Optional[int] = None
) -> PhoneChangeDecision:
    """
    Analyzes phone number changes and determines what actions are needed.

    This is a pure function that contains all the business logic for phone changes
    without any side effects (no database updates, no SMS sending).

    Args:
        current_phone: Current phone number from user record (e.g., "+18005551234")
        new_country_code: New country code from form (e.g., "+1")
        new_phone_number: New phone number from form (e.g., "8005551234")
        wks_records: List of worksheet records to check for conflicts
        current_user_row: Row number of current user to exclude from conflict checking

    Returns:
        PhoneChangeDecision with analysis of what needs to happen
    """

    # Handle empty/None inputs
    current_phone = current_phone or ""
    new_country_code = new_country_code or ""
    new_phone_number = new_phone_number or ""

    # If no phone provided, determine if we should clear existing phone
    if not new_country_code and not new_phone_number:
        if current_phone:
            return PhoneChangeDecision(clear=True, changed=True)
        else:
            return PhoneChangeDecision()  # No change needed

    # If only partial phone data provided, that's an error state
    # (This should be caught by form validation, but double-check here)
    if bool(new_country_code) != bool(new_phone_number):
        return PhoneChangeDecision(error=True)

    # Construct the new full phone number
    new_full_phone = new_country_code + new_phone_number

    # Normalize both phone numbers for comparison
    # This handles cases where phonenumbers library formats numbers differently
    def normalize_phone(phone_str):
        if not phone_str:
            return ""

        # Convert to string if it's an integer (from Google Sheets)
        phone_str = str(phone_str)

        try:
            import phonenumbers
            # Parse and reformat to ensure consistent format
            if not phone_str.startswith("+"):
                phone_str = "+" + phone_str
            parsed = phonenumbers.parse(phone_str)
            return f"+{parsed.country_code}{parsed.national_number}"
        except:
            # If parsing fails, try to add + prefix and return
            if not phone_str.startswith("+"):
                return "+" + phone_str
            return phone_str

    normalized_current = normalize_phone(current_phone)
    normalized_new = normalize_phone(new_full_phone)


    # Compare normalized phone numbers
    if normalized_current == normalized_new:
        return PhoneChangeDecision()  # No change

    # Phone number has changed - check for conflicts
    # Exclude current user from conflict checking
    phone_conflicts = [
        row for row in wks_records
        if normalize_phone(row.get("Phone Number")) == normalized_new and
           (current_user_row is None or row.get("Row") != current_user_row)
    ]

    if phone_conflicts:
        return PhoneChangeDecision(error=True, changed=True)

    # Phone changed and no conflicts - need verification
    return PhoneChangeDecision(verify=True, changed=True)


def calculate_phone_verification_decision(
    user: Dict[str, Any],
    phone_decision: PhoneChangeDecision,
    phone_subscribe: bool = False
) -> bool:
    """
    Determine if phone verification is needed based on phone change analysis.

    Verification is needed when:
    1. Phone number changed (phone_decision.verify and phone_decision.changed), OR
    2. Phone is unverified AND user wants to subscribe for phone notifications

    Pure function that decides if OTP verification should be triggered.

    Args:
        user: Current user record
        phone_decision: Result from analyze_phone_number_changes
        phone_subscribe: Whether user wants to subscribe for phone notifications

    Returns:
        bool: True if phone verification (OTP) is needed
    """
    # Case 1: Phone changed - need verification
    if phone_decision.verify and phone_decision.changed:
        return True

    # Case 2: Phone unverified but user wants to subscribe - need verification
    phone_verified = user.get("Phone number verified", "FALSE")
    phone_number = user.get("Phone Number", "")
    # Convert to string in case it's an integer from Google Sheets
    phone_number = str(phone_number) if phone_number else ""
    has_phone = bool(phone_number.strip())

    if has_phone and phone_verified == "FALSE":
        return True

    return False


def should_send_event_sms_confirmation(
    phone_verified: str,
    phone_subscribed: bool,
    has_phone_number: bool,
    event_name: Optional[str] = None,
    is_new_registration: bool = True
) -> bool:
    """
    Decide if we should send SMS confirmation for event registration.

    This determines when to send a direct SMS confirmation vs OTP verification.
    Only sends SMS for NEW event registrations, not updates to existing registrations.

    Args:
        phone_verified: User's phone verification status ("TRUE"/"FALSE")
        phone_subscribed: Whether user wants SMS notifications
        has_phone_number: Whether user has a phone number
        event_name: Name of the event (optional, for validation)
        is_new_registration: Whether this is a new event registration (True) or update (False)

    Returns:
        bool: True if SMS confirmation should be sent
    """
    return (
        is_new_registration and  # Only send SMS for new registrations, not updates
        has_phone_number and
        phone_verified == "TRUE" and
        phone_subscribed and
        event_name is not None
    )


def calculate_phone_updates(
    user: Dict[str, Any],
    form_data: Dict[str, Any],
    phone_decision: PhoneChangeDecision,
    row_number: int
) -> List[Dict[str, Any]]:
    """
    Calculates phone-related cell updates for the worksheet.

    Pure function that determines what phone updates are needed.

    Args:
        user: Current user record
        form_data: Form data with new phone information
        phone_decision: Result from analyze_phone_number_changes
        row_number: Row number in worksheet for this user

    Returns:
        List of cell update dictionaries with row, column, value
    """

    updates = []

    if phone_decision.clear:
        # Clear all phone-related fields
        updates.extend([
            {"row": row_number, "column": "Phone Number", "value": ""},
            {"row": row_number, "column": "Phone number subscribed", "value": ""},
            {"row": row_number, "column": "Phone number verified", "value": ""},
        ])

    elif phone_decision.changed:
        # Update phone number
        country_code = form_data.get("country_code", "")
        phone_number = form_data.get("phone_number", "")
        full_phone = country_code + phone_number if country_code and phone_number else ""

        updates.append({"row": row_number, "column": "Phone Number", "value": full_phone})

        # Set verification status based on whether verification is needed
        if phone_decision.verify:
            # When verification is needed, we'll set both verified=FALSE and subscription after OTP completion
            updates.append({"row": row_number, "column": "Phone number verified", "value": "FALSE"})
            # Don't set subscription here - it will be set after OTP verification
        else:
            # Phone changed but no verification needed (shouldn't happen, but handle gracefully)
            phone_subscribe = "TRUE" if form_data.get("phone_subscribe", False) else "FALSE"
            updates.append({"row": row_number, "column": "Phone number subscribed", "value": phone_subscribe})
            # Keep existing verification status

    else:
        # Phone number didn't change, but subscription preference might have
        phone_subscribe = "TRUE" if form_data.get("phone_subscribe", False) else "FALSE"
        updates.append({"row": row_number, "column": "Phone number subscribed", "value": phone_subscribe})

    return updates


def extract_phone_data_from_form(form) -> Dict[str, Any]:
    """
    Extract and structure phone data from event form.

    Pure function that extracts phone-related data from form object.

    Args:
        form: Form object with phone fields

    Returns:
        Dict with structured phone data
    """
    return {
        "country_code": getattr(form, "country_code", None).data if hasattr(form, "country_code") else "",
        "phone_number": getattr(form, "phone_number", None).data if hasattr(form, "phone_number") else "",
        "phone_subscribe": getattr(form, "phone_subscribe", None).data if hasattr(form, "phone_subscribe") else False,
        "full_phone_number": (
            (getattr(form, "country_code", None).data or "") +
            (getattr(form, "phone_number", None).data or "")
        ) if hasattr(form, "country_code") and hasattr(form, "phone_number") else ""
    }
