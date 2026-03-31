"""
Authn app admin configuration.

Registers all authn models with Django admin for user management.
Organized into modules by functionality:
- member: Member and MemberProfile admin
- contact: ContactEmail, ContactPhone admin
- security: RSAKeypair admin
"""

from .members.contact import ContactEmailAdmin, ContactPhoneAdmin
from .members.invitation import AdminInvitationAdmin
from .members.member import MemberAdmin
from .members.member_profile import MemberProfileAdmin
from .security.security import RSAKeypairAdmin

__all__ = [
    # Member
    "MemberAdmin",
    "MemberProfileAdmin",
    # Contact
    "ContactEmailAdmin",
    "ContactPhoneAdmin",
    # Invitation
    "AdminInvitationAdmin",
    # Security
    "RSAKeypairAdmin",
]
