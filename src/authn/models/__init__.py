"""
Authn app models export.

Aggregates commonly used models so callers can import from `authn.models`.
"""

from .contact import ContactEmail, ContactPhone
from .members import AdminInvitation, Member, MemberProfile
from .security import EmailAuthChallenge, RSAKeypair

__all__ = [
    # Members
    "Member",
    "MemberProfile",
    "AdminInvitation",
    # Contact
    "ContactEmail",
    "ContactPhone",
    # Security
    "EmailAuthChallenge",
    "RSAKeypair",
    # Schol (lazy export to avoid app-start model registration side effects)
    "SSOProfile",
]


def __getattr__(name):
    if name == "SSOProfile":
        from .schol import SSOProfile

        return SSOProfile
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
