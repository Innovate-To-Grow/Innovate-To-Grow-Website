"""
Authn app models export.

Aggregates commonly used models so callers can import from `authn.models`.
"""

from .contact import ContactEmail, ContactPhone
from .members import I2GMemberGroup, Member, MemberGroup, MemberProfile
from .security import RSAKeypair

__all__ = [
    # Members
    "Member",
    "MemberProfile",
    "MemberGroup",
    "I2GMemberGroup",
    # Contact
    "ContactEmail",
    "ContactPhone",
    # Security
    "RSAKeypair",
    # Schol (lazy export to avoid app-start model registration side effects)
    "SSOProfile",
]


def __getattr__(name):
    if name == "SSOProfile":
        from .schol import SSOProfile

        return SSOProfile
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
