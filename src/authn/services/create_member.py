from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from ..models import Member


class CreateMemberService:
    """Service for creating new member accounts."""

    @staticmethod
    @transaction.atomic
    def create_member(
        username: str,
        password: str,
        first_name: str,
        last_name: str,
        email: str = "",
        middle_name: str = "",
        organization: str = "",
        is_active: bool = True,
        is_active_member: bool = True,
        is_staff: bool = False,
        is_superuser: bool = False,
    ) -> dict[str, Any]:
        """
        Create a new member account.

        Args:
            username: Username for login (required, unique)
            password: Plain text password (will be hashed)
            first_name: Member's first name (required)
            last_name: Member's last name (required)
            email: Email address (optional, unique if provided)
            middle_name: Member's middle name (optional)
            organization: Organization or company name (optional)
            is_active: Whether the account is active (default: True)
            is_active_member: Whether user is an active member (default: True)
            is_staff: Whether user has staff permissions (default: False)
            is_superuser: Whether user has superuser permissions (default: False)

        Returns:
            dict: {
                "success": bool,
                "member": Member instance or None,
                "member_uuid": UUID str or None,
                "username": str,
                "error": str or None
            }

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        if not username or not username.strip():
            return {
                "success": False,
                "member": None,
                "member_uuid": None,
                "username": None,
                "error": "Username is required",
            }

        if not password or not password.strip():
            return {
                "success": False,
                "member": None,
                "member_uuid": None,
                "username": username,
                "error": "Password is required",
            }

        if not first_name or not first_name.strip():
            return {
                "success": False,
                "member": None,
                "member_uuid": None,
                "username": username,
                "error": "First name is required",
            }

        if not last_name or not last_name.strip():
            return {
                "success": False,
                "member": None,
                "member_uuid": None,
                "username": username,
                "error": "Last name is required",
            }

        try:
            # Check if username already exists
            if Member.objects.filter(username=username).exists():
                return {
                    "success": False,
                    "member": None,
                    "member_uuid": None,
                    "username": username,
                    "error": f"Username '{username}' already exists",
                }

            # Check if email already exists (if provided)
            if email and Member.objects.filter(email=email).exists():
                return {
                    "success": False,
                    "member": None,
                    "member_uuid": None,
                    "username": username,
                    "error": f"Email '{email}' already exists",
                }

            # Create the member using create_user which handles password hashing
            member = Member.objects.create_user(
                username=username.strip(),
                password=password,
                email=email.strip() if email else "",
                first_name=first_name.strip(),
                middle_name=middle_name.strip() if middle_name else "",
                last_name=last_name.strip(),
                organization=organization.strip() if organization else "",
                is_active=is_active,
                is_active_member=is_active_member,
                is_staff=is_staff,
                is_superuser=is_superuser,
            )

            return {
                "success": True,
                "member": member,
                "member_uuid": str(member.member_uuid),
                "username": member.username,
                "error": None,
            }

        except IntegrityError as e:
            return {
                "success": False,
                "member": None,
                "member_uuid": None,
                "username": username,
                "error": f"Database integrity error: {str(e)}",
            }

        except ValidationError as e:
            return {
                "success": False,
                "member": None,
                "member_uuid": None,
                "username": username,
                "error": f"Validation error: {str(e)}",
            }

        except Exception as e:
            return {
                "success": False,
                "member": None,
                "member_uuid": None,
                "username": username,
                "error": f"Unexpected error: {str(e)}",
            }
