"""
Collision detection service for checking if prospect emails/phones already exist in Members.
"""

import re
from typing import Optional
from django.db.models import Q
from ..models import Member, ContactEmail, ContactPhone


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number by removing spaces, dashes, and parentheses.
    Handles formats like +1 (555) 123-4567, +15551234567, etc.
    """
    if not phone:
        return ""
    # Remove all non-digit characters except +
    normalized = re.sub(r'[^\d+]', '', phone)
    # Ensure + is at the start if present
    if '+' not in normalized and normalized:
        # If no +, assume it starts with country code
        normalized = '+' + normalized
    return normalized


def check_email_collision(email: str) -> bool:
    """
    Check if an email address already exists in Members (via ContactEmail).
    
    Args:
        email: Email address to check
        
    Returns:
        True if email exists in Members, False otherwise
    """
    if not email:
        return False
    
    # Case-insensitive check
    email_lower = email.lower().strip()
    return ContactEmail.objects.filter(
        email_address__iexact=email_lower
    ).exists()


def check_phone_collision(phone: str) -> bool:
    """
    Check if a phone number already exists in Members (via ContactPhone).
    
    Args:
        phone: Phone number to check
        
    Returns:
        True if phone exists in Members, False otherwise
    """
    if not phone:
        return False
    
    # Normalize input phone - extract all digits
    input_digits = re.sub(r'[^\d]', '', phone)
    if not input_digits:
        return False
    
    # Check all ContactPhone records
    for contact_phone in ContactPhone.objects.all():
        # Get formatted number (e.g., "+11234567890")
        formatted = contact_phone.get_formatted_number()
        # Extract all digits from formatted number
        stored_digits = re.sub(r'[^\d]', '', formatted)
        
        # Compare - handle cases where one has country code and other doesn't
        # If stored has country code (starts with 1 for US), try matching with/without it
        if stored_digits.startswith('1') and len(stored_digits) == 11:
            # Stored: +11234567890 -> 11234567890
            # Check if input matches with or without country code
            if stored_digits == input_digits or stored_digits[1:] == input_digits:
                return True
        elif input_digits.startswith('1') and len(input_digits) == 11:
            # Input has country code, stored might not
            if input_digits == stored_digits or input_digits[1:] == stored_digits:
                return True
        else:
            # Direct comparison
            if stored_digits == input_digits:
                return True
    
    return False


def update_prospect_collisions(prospect) -> None:
    """
    Update collision fields on a Prospect instance based on current Members.
    
    Args:
        prospect: Prospect instance to update
    """
    if not prospect:
        return
    
    # Check primary email collision
    prospect.primary_collision = check_email_collision(prospect.email)
    
    # Check secondary email collision
    if prospect.secondary_email:
        prospect.secondary_collision = check_email_collision(prospect.secondary_email)
    else:
        prospect.secondary_collision = False
    
    # Check phone collision
    if prospect.phone_number:
        prospect.phone_collision = check_phone_collision(prospect.phone_number)
    else:
        prospect.phone_collision = False
    
    # Save only collision fields
    prospect.save(update_fields=[
        'primary_collision',
        'secondary_collision',
        'phone_collision'
    ])
