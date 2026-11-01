"""The application roles an access token claims: diagnostic evidence for the access check, never trusted.

Microsoft documents decoding access tokens "for validation and debugging purposes only", and the site never decides
access from them: Microsoft does. Every Entra application permission the app holds (admin consent) is listed in the
token's ``roles`` claim; Exchange Online RBAC for Applications grants never are, so an empty list is not proof that
the app has no other permission. The mailbox probes show what Microsoft really allows.
"""

import base64
import binascii
import json

from django.conf import settings

from apps.core.utils.security import is_graph_permission

from .report import FAIL, INCONCLUSIVE, PASS, ROLES, WARN, ProbeResult

# A claim with more roles, or with any value that is not a permission name, counts as unreadable (and is not echoed).
MAX_ROLES = 64
NO_ROLES = (
    "the token claims no application roles; RBAC for Applications grants never appear there, so only the mailbox "
    "probes show what Microsoft allows"
)
UNREADABLE = "the token's roles could not be read, so this run cannot show they are within the approval"


def approved_roles() -> tuple[str, ...]:
    return tuple(sorted(set(settings.GRAPH_APPROVED_APPLICATION_ROLES)))


def token_roles(token: str) -> tuple[str, ...] | None:
    """The sorted ``roles`` claim of a JWT access token, read WITHOUT verifying it; None when it cannot be read."""
    parts = str(token).split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, binascii.Error, RecursionError):
        return None
    roles = payload.get("roles", []) if isinstance(payload, dict) else None
    if not isinstance(roles, list) or len(roles) > MAX_ROLES:
        return None
    if not all(is_graph_permission(role) for role in roles):
        return None
    return tuple(sorted(set(roles)))


def roles_result(granted: tuple[str, ...] | None, approved: tuple[str, ...], exception_reference: str) -> ProbeResult:
    """FAIL for roles beyond the approval (WARN when an InfoSec exception is recorded); WARN when there are none.

    Unreadable roles are INCONCLUSIVE: the run then is not a complete validation.
    """
    expected = f"within {', '.join(approved)}"
    if granted is None:
        return ProbeResult(ROLES, "-", expected, INCONCLUSIVE, note=UNREADABLE)
    if not granted:
        return ProbeResult(ROLES, "-", expected, WARN, note=NO_ROLES)
    extra = sorted(set(granted) - set(approved))
    note = f"granted {', '.join(granted)}"
    if not extra:
        return ProbeResult(ROLES, "-", expected, PASS, note=note)
    note = f"{note}; beyond the approval: {', '.join(extra)}"
    if exception_reference:
        return ProbeResult(ROLES, "-", expected, WARN, note=f"{note}; InfoSec exception {exception_reference}")
    return ProbeResult(ROLES, "-", expected, FAIL, note=f"{note}; needs OIT to remove them or an InfoSec review")
