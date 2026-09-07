from __future__ import annotations

from rest_framework.exceptions import NotAuthenticated

from .constants import AUTHENTICATED_OPERATIONS, PRINCIPAL_MEMBER, PRINCIPAL_SESSION
from .exceptions import SendVerificationUnavailable
from .hashing import hash_value


def authenticate_for_operation(request, operation: str) -> None:
    """Match the authentication policy of the operation's sending endpoint."""
    if operation not in AUTHENTICATED_OPERATIONS:
        return
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return
    from rest_framework_simplejwt.authentication import JWTAuthentication

    authenticated = JWTAuthentication().authenticate(request)
    if authenticated is None:
        raise NotAuthenticated()
    request.user, request.auth = authenticated


def principal_from_request(request, *, operation: str) -> tuple[str, str]:
    user = getattr(request, "user", None)
    if operation in AUTHENTICATED_OPERATIONS:
        if user is None or not getattr(user, "is_authenticated", False):
            raise NotAuthenticated()
        return PRINCIPAL_MEMBER, str(user.pk)
    session = getattr(request, "session", None)
    session_key = getattr(session, "session_key", None) if session is not None else None
    if session is not None and not session_key:
        session.save()
        session_key = session.session_key
    if session_key:
        return PRINCIPAL_SESSION, hash_value(session_key)
    raise SendVerificationUnavailable("A verification session is required.")


def principals_match(left_type: str, left_key: str, right_type: str, right_key: str) -> bool:
    return left_type == right_type and left_key == right_key
