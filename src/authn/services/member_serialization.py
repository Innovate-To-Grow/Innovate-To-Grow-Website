"""
Serialization utilities for converting Members and Prospects to/from Google Sheets row format.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from django.utils import timezone
from django.utils.dateformat import format

from ..models import Member, Prospect, ContactEmail, ContactPhone, MemberContactInfo


def format_datetime(dt: Optional[datetime]) -> str:
    """
    Format datetime for Google Sheets display.
    Returns format like "2024-01-15 2:30 PM"
    """
    if not dt:
        return ""
    # Convert to local timezone if needed, then format
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%Y-%m-%d %I:%M %p")


def parse_datetime(date_str: str) -> Optional[datetime]:
    """
    Parse datetime string from Google Sheets.
    Handles various formats.
    Returns timezone-aware datetime.
    """
    if not date_str or not date_str.strip():
        return None
    
    date_str = date_str.strip()
    
    # Try common formats
    formats = [
        "%Y-%m-%d %I:%M %p",  # 2024-01-15 2:30 PM
        "%Y-%m-%d %H:%M",      # 2024-01-15 14:30
        "%Y-%m-%d",             # 2024-01-15
        "%m/%d/%Y %I:%M %p",    # 01/15/2024 2:30 PM
        "%m/%d/%Y",              # 01/15/2024
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Make timezone-aware (assume local timezone)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
        except ValueError:
            continue
    
    return None


def bool_to_sheet(value: Optional[bool]) -> str:
    """Convert boolean to sheet-friendly string."""
    if value is True:
        return "Yes"
    elif value is False:
        return "No"
    return ""


def sheet_to_bool(value: Any) -> bool:
    """Convert sheet value to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value_lower = value.lower().strip()
        return value_lower in ('yes', 'true', '1', 'y')
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def member_to_row(member: Member, order: int = 0) -> List[str]:
    """
    Convert a Member instance to a Google Sheets row format.
    
    Columns: Order, First Name, Last Name, When Started, Last Updated, 
    Primary Email, Primary Verified, Primary Subscribed, Primary Expired, Primary Bounced,
    Secondary Email, Secondary Verified, Secondary Subscribed, Secondary Expired, Secondary Bounced,
    Phone Number, Phone number subscribed, Phone number verified, Info Completed
    """
    # Get primary contact info
    contact_info = member.get_primary_contact_info()
    
    # Get primary and secondary emails
    primary_email = ""
    primary_verified = False
    primary_subscribed = False
    primary_expired = False
    primary_bounced = False
    
    secondary_email = ""
    secondary_verified = False
    secondary_subscribed = False
    secondary_expired = False
    secondary_bounced = False
    
    phone_number = ""
    phone_subscribed = False
    phone_verified = False
    
    if contact_info:
        # Primary email
        if contact_info.contact_email:
            email = contact_info.contact_email
            if email.email_type == 'primary':
                primary_email = email.email_address
                primary_verified = email.verified
                primary_subscribed = email.subscribe
                primary_expired = email.expired
                primary_bounced = email.bounced
        
        # Phone
        if contact_info.contact_phone:
            phone = contact_info.contact_phone
            phone_number = phone.get_formatted_number()
            phone_subscribed = phone.subscribe
            # Note: ContactPhone doesn't have verified field, so we'll use False
            phone_verified = False
    
    # Get all contact infos to find secondary email
    all_contact_infos = MemberContactInfo.objects.filter(model_user=member)
    for ci in all_contact_infos:
        if ci.contact_email and ci.contact_email.email_type == 'secondary':
            email = ci.contact_email
            secondary_email = email.email_address
            secondary_verified = email.verified
            secondary_subscribed = email.subscribe
            secondary_expired = email.expired
            secondary_bounced = email.bounced
            break
    
    # When Started = date_joined
    when_started = format_datetime(member.date_joined)
    
    # Last Updated = updated_at from most recent contact info or date_joined
    last_updated = when_started
    if contact_info:
        last_updated = format_datetime(contact_info.updated_at)
    
    # Info Completed - check if member has complete info
    info_completed = bool(
        member.first_name and 
        member.last_name and 
        primary_email and
        (phone_number or secondary_email)
    )
    
    return [
        str(order),  # Order
        member.first_name or "",  # First Name
        member.last_name or "",  # Last Name
        when_started,  # When Started
        last_updated,  # Last Updated
        primary_email,  # Primary Email
        bool_to_sheet(primary_verified),  # Primary Verified
        bool_to_sheet(primary_subscribed),  # Primary Subscribed
        bool_to_sheet(primary_expired),  # Primary Expired
        bool_to_sheet(primary_bounced),  # Primary Bounced
        secondary_email,  # Secondary Email
        bool_to_sheet(secondary_verified),  # Secondary Verified
        bool_to_sheet(secondary_subscribed),  # Secondary Subscribed
        bool_to_sheet(secondary_expired),  # Secondary Expired
        bool_to_sheet(secondary_bounced),  # Secondary Bounced
        phone_number,  # Phone Number
        bool_to_sheet(phone_subscribed),  # Phone number subscribed
        bool_to_sheet(phone_verified),  # Phone number verified
        bool_to_sheet(info_completed),  # Info Completed
    ]


def prospect_to_row(prospect: Prospect) -> List[str]:
    """
    Convert a Prospect instance to a Google Sheets row format.
    
    Columns: First Name (optional), Last Name (optional), Email, When Input?, 
    When signed up as member?, When last checked?, Bounced (when)?, Collision?,
    Secondary Email (optional), Secondary Bounced (when)?, Secondary Collision,
    Phone Number (optional), Phone Bounced (when)?, Phone Collision, Notes
    """
    return [
        prospect.first_name or "",  # First Name (optional)
        prospect.last_name or "",  # Last Name (optional)
        prospect.email,  # Email
        format_datetime(prospect.when_input),  # When Input?
        format_datetime(prospect.when_signed_up_as_member),  # When signed up as member?
        format_datetime(prospect.when_last_checked),  # When last checked?
        format_datetime(prospect.primary_bounced_at),  # Bounced (when)?
        bool_to_sheet(prospect.primary_collision),  # Collision?
        prospect.secondary_email or "",  # Secondary Email (optional)
        format_datetime(prospect.secondary_bounced_at),  # Secondary Bounced (when)?
        bool_to_sheet(prospect.secondary_collision),  # Secondary Collision
        prospect.phone_number or "",  # Phone Number (optional)
        format_datetime(prospect.phone_bounced_at),  # Phone Bounced (when)?
        bool_to_sheet(prospect.phone_collision),  # Phone Collision
        prospect.notes or "",  # Notes
    ]


def row_to_member(row: Dict[str, Any], headers: List[str]) -> Optional[Member]:
    """
    Convert a Google Sheets row (as dict) to Member instance.
    Creates or updates the member.
    
    Note: This is a simplified version. Full implementation would need to handle
    creating/updating ContactEmail and ContactPhone records.
    """
    # This is complex - would need to handle creating/updating related ContactEmail/ContactPhone
    # For now, return None - this will be implemented in the sync service
    # where we have more context about how to handle updates
    return None


def row_to_prospect(row: Dict[str, Any], headers: List[str]) -> Optional[Prospect]:
    """
    Convert a Google Sheets row (as dict) to Prospect instance.
    Creates or updates the prospect.
    """
    # Map headers to values
    row_dict = dict(zip(headers, row))
    
    email = row_dict.get('Email', '').strip()
    if not email:
        return None
    
    # Get or create prospect by email
    prospect, created = Prospect.objects.get_or_create(
        email=email,
        defaults={
            'first_name': row_dict.get('First Name (optional)', '').strip() or None,
            'last_name': row_dict.get('Last Name (optional)', '').strip() or None,
            'secondary_email': row_dict.get('Secondary Email (optional)', '').strip() or None,
            'phone_number': row_dict.get('Phone Number (optional)', '').strip() or None,
            'notes': row_dict.get('Notes', '').strip(),
        }
    )
    
    # Update fields
    if not created:
        prospect.first_name = row_dict.get('First Name (optional)', '').strip() or None
        prospect.last_name = row_dict.get('Last Name (optional)', '').strip() or None
        prospect.secondary_email = row_dict.get('Secondary Email (optional)', '').strip() or None
        prospect.phone_number = row_dict.get('Phone Number (optional)', '').strip() or None
        prospect.notes = row_dict.get('Notes', '').strip()
    
    # Parse dates
    when_input_str = row_dict.get('When Input?', '').strip()
    if when_input_str:
        dt = parse_datetime(when_input_str)
        if dt:
            prospect.when_input = dt
    
    when_signed_up_str = row_dict.get('When signed up as member?', '').strip()
    if when_signed_up_str:
        dt = parse_datetime(when_signed_up_str)
        if dt:
            prospect.when_signed_up_as_member = dt
    
    when_last_checked_str = row_dict.get('When last checked?', '').strip()
    if when_last_checked_str:
        dt = parse_datetime(when_last_checked_str)
        if dt:
            prospect.when_last_checked = dt
    
    primary_bounced_str = row_dict.get('Bounced (when)?', '').strip()
    if primary_bounced_str:
        dt = parse_datetime(primary_bounced_str)
        if dt:
            prospect.primary_bounced_at = dt
    else:
        prospect.primary_bounced_at = None
    
    secondary_bounced_str = row_dict.get('Secondary Bounced (when)?', '').strip()
    if secondary_bounced_str:
        dt = parse_datetime(secondary_bounced_str)
        if dt:
            prospect.secondary_bounced_at = dt
    else:
        prospect.secondary_bounced_at = None
    
    phone_bounced_str = row_dict.get('Phone Bounced (when)?', '').strip()
    if phone_bounced_str:
        dt = parse_datetime(phone_bounced_str)
        if dt:
            prospect.phone_bounced_at = dt
    else:
        prospect.phone_bounced_at = None
    
    # Parse booleans
    prospect.primary_collision = sheet_to_bool(row_dict.get('Collision?', ''))
    prospect.secondary_collision = sheet_to_bool(row_dict.get('Secondary Collision', ''))
    prospect.phone_collision = sheet_to_bool(row_dict.get('Phone Collision', ''))
    
    prospect.save()
    return prospect
