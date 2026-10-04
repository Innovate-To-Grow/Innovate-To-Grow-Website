"""
Shared helpers for auth API responses.
"""

from collections.abc import Mapping

from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authn.constants import VERIFICATION_INVALID, VERIFICATION_THROTTLED
from apps.authn.services import (
    AuthChallengeDeliveryError,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
    PhoneVerificationDeliveryError,
    PhoneVerificationThrottled,
)

# Longest string ``read_body_string`` hands on; anything longer reads as "missing". The credentials these views take
# are all far shorter: ``LoginLinkToken.token`` and ``ImpersonationToken.token`` are ``secrets.token_urlsafe(48)``
# (64 characters) in columns capped at ``max_length=128``, so a longer string can never match a row.
# 2048 leaves 16x headroom over that column cap, so no real credential can be rejected here, while a value
# of megabytes never reaches a query. Do not rely on Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE`` for that: DRF before
# 3.18 parsed a JSON body from the stream past it, and a body under the cap can still hold a megabyte-long value.
MAX_CREDENTIAL_LENGTH = 2048


def read_body_string(request, key: str) -> str:
    """Return ``request.data[key]`` stripped, or ``""`` when it is absent, blank or unusable as a credential.

    A JSON body may be any value (``null``, a list, ...) and a field may hold a number, list or object;
    both must read as "missing" so the caller can answer 400 instead of raising ``AttributeError``.
    A string the database layer cannot take (a lone surrogate such as ``"\\ud800"``, which cannot be
    UTF-8 encoded, or a NUL character, which PostgreSQL rejects) also reads as "missing": it can never
    be a real credential, and looking it up would be a 500 instead of the view's normal 400.
    So does one longer than ``MAX_CREDENTIAL_LENGTH`` once stripped, which is never a real credential either.
    """
    data = request.data
    value = data.get(key, "") if isinstance(data, Mapping) else ""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if len(value) > MAX_CREDENTIAL_LENGTH:
        return ""
    if "\x00" in value:
        return ""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return ""
    return value


def build_auth_success_payload(
    member,
    message: str,
    *,
    next_step: str | None = None,
    requires_profile_completion: bool | None = None,
) -> dict:
    resolved_requires_profile_completion = (
        bool(requires_profile_completion)
        if requires_profile_completion is not None
        else bool(getattr(member, "requires_profile_completion", False))
    )
    resolved_next_step = next_step or ("complete_profile" if resolved_requires_profile_completion else "account")
    refresh = RefreshToken.for_user(member)
    payload = {
        "message": message,
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "member_uuid": str(member.member_uuid),
            "email": member.get_primary_email(),
            "phone": member.get_primary_phone(),
            "is_staff": member.is_staff,
        },
        "next_step": resolved_next_step,
        "requires_profile_completion": resolved_requires_profile_completion,
    }
    return payload


def challenge_error_response(exc: Exception) -> Response:
    if isinstance(exc, AuthChallengeInvalid):
        return Response({"detail": VERIFICATION_INVALID}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, AuthChallengeThrottled):
        return Response({"detail": VERIFICATION_THROTTLED}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if isinstance(exc, AuthChallengeDeliveryError):
        return Response({"detail": "Failed to send verification email."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, PhoneVerificationThrottled):
        return Response({"detail": VERIFICATION_THROTTLED}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if isinstance(exc, PhoneVerificationDeliveryError):
        return Response({"detail": "Failed to send verification SMS."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    raise exc
