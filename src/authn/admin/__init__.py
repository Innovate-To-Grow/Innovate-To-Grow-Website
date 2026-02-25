"""
Authn app admin configuration.

Registers all authn models with Django admin for user management.
Organized into modules by functionality:
- member: Member and MemberProfile admin
- group: I2GMemberGroup admin
- contact: ContactEmail, ContactPhone admin
- security: RSAKeypair admin
"""

from .members.contact import ContactEmailAdmin, ContactPhoneAdmin
from .members.group import I2GMemberGroupAdmin
from .members.member import MemberAdmin, MemberProfileAdmin
from .security.security import RSAKeypairAdmin

__all__ = [
    # Member
    "MemberAdmin",
    "MemberProfileAdmin",
    # Group
    "I2GMemberGroupAdmin",
    # Contact
    "ContactEmailAdmin",
    "ContactPhoneAdmin",
    # Security
    "RSAKeypairAdmin",
]
