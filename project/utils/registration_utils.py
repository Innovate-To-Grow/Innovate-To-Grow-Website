"""
Registration Utils - Pure Business Logic Functions

This module contains pure functions for handling complete registration business logic.
These functions are separated from side effects to enable better testing, maintainability,
and reusability.

Functions in this module analyze complete registration scenarios where:
- User doesn't exist in the system yet
- Primary email is immediately verified (comes from token)
- Secondary email needs conflict checking and verification
- All profile information is collected in a single step
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class CompleteRegistrationDecision:
    """
    Represents the analysis of a complete registration attempt.

    Attributes:
        can_proceed: Whether the registration can proceed without conflicts
        emails_to_clear: List of cell updates needed to clear expired conflicting emails
        notification_emails: List of notification emails to send to affected users
        conflict_details: Details about any conflicts found (for debugging/logging)
    """
    can_proceed: bool
    emails_to_clear: List[Dict[str, Any]]  # [{"row": int, "column": str, "value": str}]
    notification_emails: List[Dict[str, Any]]  # [{"to": str, "type": str, "user_first_name": str, ...}]
    conflict_details: Dict[str, Any]


def analyze_complete_registration_conflicts(
    wks_records: List[Dict[str, Any]],
    primary_email: str,
    secondary_email: str
) -> CompleteRegistrationDecision:
    """
    Analyzes potential conflicts for a complete registration attempt.

    Since complete registration is for NEW users only, we need to check:
    1. Primary email doesn't exist anywhere (should be guaranteed by caller)
    2. Secondary email conflicts with existing users

    For secondary email conflicts:
    - If conflicting email is expired → clear it and send notification
    - If conflicting email is active → block registration

    Args:
        wks_records: List of existing user records from membership worksheet
        primary_email: Primary email address (from token, should be unique)
        secondary_email: Secondary email address entered by user

    Returns:
        CompleteRegistrationDecision with analysis results
    """
    emails_to_clear = []
    notification_emails = []
    conflict_details = {"secondary_conflicts": []}
    can_proceed = True
    
    # Convert emails to lowercase for case-insensitive comparison
    secondary_email_lower = secondary_email.lower()
    
    # Check secondary email against both primary and secondary columns
    secondary_validations = [
        (secondary_email_lower, "Primary Email"),
        (secondary_email_lower, "Secondary Email")
    ]
    
    # First pass: collect all conflicts and determine if any are blocking
    all_conflicts = []
    has_active_conflict = False
    
    for email_to_check, column_to_search in secondary_validations:
        # Find existing users with this email in this column (case-insensitive)
        matching_users = [row for row in wks_records if row[column_to_search].lower() == email_to_check]
        
        if not matching_users:
            continue  # No conflict
            
        existing_user = matching_users[0]  # Take first match
        existing_user_row = existing_user["Row"]
        
        # Determine the relevant fields based on column
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
        
        # Check if this conflict is active (blocking)
        is_active = existing_user[expired_field] == "FALSE"
        if is_active:
            has_active_conflict = True
        
        # Record conflict details
        conflict_info = {
            "existing_user_row": existing_user_row,
            "existing_user_name": f"{existing_user['First Name']} {existing_user['Last Name']}",
            "conflicting_email": secondary_email,  # Use original email for display
            "column": column_to_search,
            "expired_status": existing_user[expired_field],
            "verified_status": existing_user[verified_field],
            "existing_user": existing_user,
            "expired_field": expired_field,
            "other_email_field": other_email_field,
            "other_verified_field": other_verified_field,
            "email_being_cleared": email_being_cleared,
            "is_active": is_active
        }
        all_conflicts.append(conflict_info)
    
    # Second pass: determine actions based on whether any conflict is active
    if has_active_conflict:
        # If ANY conflict is active, block the entire registration
        can_proceed = False
        for conflict_info in all_conflicts:
            conflict_info["action"] = "blocked"
            conflict_details["secondary_conflicts"].append({
                "existing_user_row": conflict_info["existing_user_row"],
                "existing_user_name": conflict_info["existing_user_name"],
                "conflicting_email": conflict_info["conflicting_email"],
                "column": conflict_info["column"],
                "expired_status": conflict_info["expired_status"],
                "verified_status": conflict_info["verified_status"],
                "action": "blocked"
            })
    else:
        # All conflicts are expired, we can clear them
        can_proceed = True
        for conflict_info in all_conflicts:
            conflict_info["action"] = "cleared"
            conflict_details["secondary_conflicts"].append({
                "existing_user_row": conflict_info["existing_user_row"],
                "existing_user_name": conflict_info["existing_user_name"],
                "conflicting_email": conflict_info["conflicting_email"],
                "column": conflict_info["column"],
                "expired_status": conflict_info["expired_status"],
                "verified_status": conflict_info["verified_status"],
                "action": "cleared"
            })
            
            # Add cell update to clear the expired email
            emails_to_clear.append({
                "row": conflict_info["existing_user_row"],
                "column": conflict_info["column"],
                "value": ""  # Clear the email
            })
            
            # Send notification email if the user has another verified email
            existing_user = conflict_info["existing_user"]
            other_email = existing_user[conflict_info["other_email_field"]]
            if other_email != "" and existing_user[conflict_info["other_verified_field"]] == "TRUE":
                notification_emails.append({
                    "to": other_email,
                    "type": "deletion_notice",
                    "user_first_name": existing_user["First Name"],
                    "user_last_name": existing_user["Last Name"],
                    "deleted_email": conflict_info["email_being_cleared"]
                })

    return CompleteRegistrationDecision(
        can_proceed=can_proceed,
        emails_to_clear=emails_to_clear,
        notification_emails=notification_emails,
        conflict_details=conflict_details
    )


def calculate_new_user_creation(
    form_data: Dict[str, Any],
    custom_fields: List[Dict[str, Any]],
    next_order_number: int,
    current_timestamp: str
) -> Dict[str, Any]:
    """
    Calculates all the data needed to create a new user record for complete registration.

    For complete registration, the user record has special characteristics:
    - Primary email is immediately verified and subscribed
    - Secondary email is unverified and unsubscribed
    - Info is marked as completed immediately
    - All custom fields are filled from the form

    Args:
        form_data: Form data containing all user information
        custom_fields: List of custom field definitions with labels and types
        next_order_number: The next order number for this user
        current_timestamp: Current timestamp string for creation tracking

    Returns:
        Dictionary with all user data mapped to column names
    """
    user_data = {
        # Basic identification and tracking
        "Order": next_order_number,
        "First Name": form_data["first_name"],
        "Last Name": form_data["last_name"],
        "When Started": current_timestamp,
        "Last Updated": current_timestamp,

        # Primary email (immediately verified in complete registration)
        "Primary Email": form_data["primary_email"],
        "Primary Verified": "TRUE",      # Key difference: immediately verified
        "Primary Subscribed": "TRUE",    # Key difference: auto-subscribed
        "Primary Expired": "FALSE",
        "Primary Bounced": "",

        # Secondary email (needs verification)
        "Secondary Email": form_data["secondary_email"],
        "Secondary Verified": "FALSE",   # Will be verified later
        "Secondary Subscribed": "FALSE", # Cannot subscribe unverified email
        "Secondary Expired": "FALSE",
        "Secondary Bounced": "",

        # Completion status
        "Info Completed": "TRUE"         # Key difference: immediately completed
    }

    # Add phone fields if provided
    if "phone_data" in form_data:
        user_data.update(form_data["phone_data"])

    # Add custom fields
    for field in custom_fields:
        field_name = field["label"]
        if field_name in form_data:
            if field["field_type"] == "Checkbox":
                # Handle checkbox fields (convert list to newline-separated string)
                if isinstance(form_data[field_name], list):
                    user_data[field_name] = "\n".join(form_data[field_name])
                else:
                    user_data[field_name] = form_data[field_name] or ""
            else:
                user_data[field_name] = form_data[field_name] or ""

    return user_data


def calculate_event_registration_from_complete(
    form_data: Dict[str, Any],
    event_questions: List[str],
    register_for_event: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Calculates event registration data if user opted to register for an event.

    This extracts event-specific data from the complete registration form
    and formats it for event worksheet creation.

    Args:
        form_data: Complete form data including event fields
        event_questions: List of event-specific question field names
        register_for_event: Whether user opted to register for the event

    Returns:
        Dictionary with event registration data, or None if not registering
    """
    if not register_for_event:
        return None

    event_data = {}

    # Extract ticket type if present
    if "event_tickets" in form_data:
        event_data["Ticket Type"] = form_data["event_tickets"]

    # Extract answers to event-specific questions
    for question in event_questions:
        event_field_key = f"event_{question}"
        if event_field_key in form_data:
            event_data[question] = form_data[event_field_key] or ""

    return event_data if event_data else None


def validate_complete_registration_form_data(
    form_data: Dict[str, Any],
    required_fields: List[str] = None
) -> Dict[str, List[str]]:
    """
    Validates complete registration form data for business rule compliance.

    Checks for required fields, email format validation, and business rules
    specific to complete registration.

    Args:
        form_data: Form data to validate
        required_fields: List of field names that are required (optional)

    Returns:
        Dictionary mapping field names to lists of error messages
    """
    errors = {}

    # Default required fields for complete registration
    if required_fields is None:
        required_fields = ["first_name", "last_name", "primary_email", "secondary_email"]

    # Check required fields
    for field in required_fields:
        if not form_data.get(field, "").strip():
            if field not in errors:
                errors[field] = []
            errors[field].append(f"{field.replace('_', ' ').title()} is required")

    # Business rule: primary and secondary emails must be different
    primary = form_data.get("primary_email", "").strip().lower()
    secondary = form_data.get("secondary_email", "").strip().lower()

    if primary and secondary and primary == secondary:
        if "secondary_email" not in errors:
            errors["secondary_email"] = []
        errors["secondary_email"].append("Secondary email must be different from primary email")

    # Email format validation (basic check)
    for email_field in ["primary_email", "secondary_email"]:
        email = form_data.get(email_field, "").strip()
        if email and "@" not in email:
            if email_field not in errors:
                errors[email_field] = []
            errors[email_field].append("Invalid email format")

    return errors


def analyze_user_existence_check(
    wks_records: List[Dict[str, Any]],
    primary_email: str,
    secondary_email: str
) -> Dict[str, Any]:
    """
    Checks if a user already exists with either of the provided emails.

    For complete registration, the user should NOT exist in the system.
    This function helps determine if we should proceed or redirect to update flow.

    Args:
        wks_records: List of existing user records
        primary_email: Primary email to check
        secondary_email: Secondary email to check

    Returns:
        Dictionary with existence analysis results
    """
    primary_matches = []
    secondary_matches = []

    # Convert emails to lowercase for case-insensitive comparison
    primary_email_lower = primary_email.lower()
    secondary_email_lower = secondary_email.lower()

    # Check primary email against both columns
    for row in wks_records:
        if row["Primary Email"].lower() == primary_email_lower:
            primary_matches.append({"row": row, "found_in": "Primary Email"})
        elif row["Secondary Email"].lower() == primary_email_lower:
            primary_matches.append({"row": row, "found_in": "Secondary Email"})

    # Check secondary email against both columns  
    for row in wks_records:
        if row["Primary Email"].lower() == secondary_email_lower:
            secondary_matches.append({"row": row, "found_in": "Primary Email"})
        elif row["Secondary Email"].lower() == secondary_email_lower:
            secondary_matches.append({"row": row, "found_in": "Secondary Email"})

    # Determine if user exists
    user_exists = len(primary_matches) > 0 or len(secondary_matches) > 0

    # Find the existing user record if any
    existing_user = None
    if primary_matches:
        existing_user = primary_matches[0]["row"]
    elif secondary_matches:
        existing_user = secondary_matches[0]["row"]

    return {
        "user_exists": user_exists,
        "existing_user": existing_user,
        "primary_email_matches": primary_matches,
        "secondary_email_matches": secondary_matches,
        "should_use_complete_registration": not user_exists,
        "should_redirect_to_update": user_exists
    }


def analyze_phone_number_conflicts(
    wks_records: List[Dict[str, Any]], 
    phone_number: str
) -> Dict[str, Any]:
    """
    Analyzes potential conflicts for a phone number in complete registration.
    
    Args:
        wks_records: List of existing user records from membership worksheet
        phone_number: Full international phone number (e.g., "+15551234567")
    
    Returns:
        Dictionary with conflict analysis results
    """
    if not phone_number or phone_number.strip() == "":
        return {
            "has_conflict": False,
            "conflicting_user": None,
            "can_proceed": True,
            "conflict_details": None
        }
    
    # Find users with this phone number
    phone_number_clean = phone_number.strip()
    matching_users = [row for row in wks_records 
                     if row.get("Phone Number") is not None 
                     and str(row.get("Phone Number", "")).strip() == phone_number_clean]
    
    if not matching_users:
        return {
            "has_conflict": False,
            "conflicting_user": None,
            "can_proceed": True,
            "conflict_details": None
        }
    
    # Phone number conflict found
    conflicting_user = matching_users[0]  # Take first match
    
    # Handle malformed records gracefully
    user_row = conflicting_user.get("Row", "Unknown")
    first_name = conflicting_user.get("First Name", "Unknown")
    last_name = conflicting_user.get("Last Name", "User")
    
    conflict_details = {
        "existing_user_row": user_row,
        "existing_user_name": f"{first_name} {last_name}",
        "phone_number": phone_number_clean,
        "existing_user": conflicting_user
    }
    
    return {
        "has_conflict": True,
        "conflicting_user": conflicting_user,
        "can_proceed": False,  # Phone numbers must be unique
        "conflict_details": conflict_details
    }


def calculate_registration_method(
    has_secondary_email: bool, 
    has_phone_number: bool
) -> str:
    """
    Determines the registration method based on provided contact methods.
    
    Args:
        has_secondary_email: Whether a secondary email was provided
        has_phone_number: Whether a phone number was provided
    
    Returns:
        String representing registration method:
        - "1": Primary + Secondary emails only
        - "2": Primary email + Phone number only  
        - "3": All three methods (Primary email + Secondary email + Phone)
    """
    if has_secondary_email and has_phone_number:
        return "3"  # All three methods
    elif has_secondary_email:
        return "1"  # Two emails only
    elif has_phone_number:
        return "2"  # Email + phone only
    else:
        # This shouldn't happen due to form validation, but default to emails only
        return "1"


def should_trigger_phone_verification(
    registration_method: str,
    phone_number: str
) -> bool:
    """
    Determines if phone verification (OTP) should be triggered.
    
    Args:
        registration_method: Registration method ("1", "2", or "3")
        phone_number: Full international phone number
    
    Returns:
        Boolean indicating if phone verification is needed
    """
    # Phone verification is required for methods 2 and 3 (when phone is provided)
    has_phone = bool(phone_number and phone_number.strip())
    needs_verification = registration_method in ["2", "3"]
    
    return has_phone and needs_verification


def validate_and_format_phone_number(
    country_code: str,
    phone_number: str
) -> Dict[str, Any]:
    """
    Validates and formats a phone number for storage.
    
    Args:
        country_code: Country code (e.g., "+1")
        phone_number: National phone number (e.g., "5551234567")
    
    Returns:
        Dictionary with validation results and formatted phone number
    """
    if not phone_number or phone_number.strip() == "":
        return {
            "is_valid": True,
            "formatted_number": "",
            "error_message": None
        }
    
    if not country_code or country_code.strip() == "":
        return {
            "is_valid": False,
            "formatted_number": "",
            "error_message": "Country code is required when phone number is provided"
        }
    
    # Basic validation - ensure phone number contains only digits, spaces, hyphens, parentheses
    import re
    phone_clean = re.sub(r'[^\d]', '', phone_number.strip())
    
    if not phone_clean:
        return {
            "is_valid": False,
            "formatted_number": "",
            "error_message": "Invalid phone number format"
        }
    
    # Format as international number
    formatted_number = country_code.strip() + phone_clean
    
    return {
        "is_valid": True,
        "formatted_number": formatted_number,
        "error_message": None
    }


def calculate_phone_registration_data(
    form_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculates phone-related data for user registration.
    
    Args:
        form_data: Form data containing phone information
    
    Returns:
        Dictionary with phone data for user record
    """
    phone_validation = validate_and_format_phone_number(
        form_data.get("country_code", ""),
        form_data.get("phone_number", "")
    )
    
    if not phone_validation["is_valid"]:
        raise ValueError(f"Phone validation failed: {phone_validation['error_message']}")
    
    phone_subscribe = "TRUE" if form_data.get("phone_subscribe", False) else "FALSE"
    
    return {
        "Phone Number": phone_validation["formatted_number"],
        "Phone number subscribed": phone_subscribe,
        "Phone number verified": "FALSE"  # Will be set to TRUE after OTP verification
    }
