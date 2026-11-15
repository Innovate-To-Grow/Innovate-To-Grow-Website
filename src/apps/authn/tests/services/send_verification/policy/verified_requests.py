from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from altcha import Payload, create_challenge, solve_challenge
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.authn.models import (
    SendVerificationChallenge,
)
from apps.authn.services.send_verification.guard.http import guarded_send
from apps.authn.services.send_verification.rules.config import load_settings
from apps.authn.services.send_verification.rules.constants import OP_LOGIN_REQUEST_CODE, OP_PHONE_AUTH_REQUEST_CODE
from apps.authn.services.send_verification.rules.hashing import hash_value
from apps.authn.services.sms import start_phone_verification

SMS_BUDGET_SPENT_ANSWER = {
    "code": "send_throttled",
    "detail": "The SMS sending budget for today has been reached.",
    "retry_after": 3600,
}


def verified_request(
    *, destination="member@example.com", operation=OP_LOGIN_REQUEST_CODE, kind="email", request_id=None
):
    config = load_settings()
    expires_at = timezone.now() + timedelta(minutes=5)
    row = SendVerificationChallenge.objects.create(
        operation=operation,
        destination_kind=kind,
        destination_normalized=destination,
        principal_type="session",
        principal_key=hash_value("shared-test-session"),
        algorithm=config.algorithm,
        cost=config.cost,
        expires_at=expires_at,
    )
    challenge = create_challenge(
        algorithm=config.algorithm,
        cost=config.cost,
        expires_at=expires_at,
        hmac_secret=config.hmac_secret,
        hmac_key_secret=config.hmac_key_secret or None,
        data={"challenge_id": str(row.pk), "operation": operation},
    )
    solution = solve_challenge(challenge)
    assert solution is not None
    return SimpleNamespace(
        data={
            "verification_challenge_id": str(row.pk),
            "verification_payload": Payload(challenge, solution).to_base64(),
            "send_request_id": str(request_id or uuid4()),
        },
        user=AnonymousUser(),
        session=SimpleNamespace(session_key="shared-test-session"),
    )


def send(request, provider, *, destination="member@example.com", operation=OP_LOGIN_REQUEST_CODE, channel="email"):
    return guarded_send(
        request,
        operation=operation,
        destination_kind="phone" if channel == "sms" else "email",
        destination_normalized=destination,
        fingerprint=hash_value(destination),
        channel=channel,
        perform=lambda: (provider(), 202),
    )


def send_sms(request, destination):
    """A protected passwordless-phone send through the real SMS service (the caller replaces the provider)."""

    def perform():
        started = start_phone_verification(destination, purpose="phone_auth", context_identifier="1-US")
        return {"challenge_id": started["challenge_id"]}, 202

    return guarded_send(
        request,
        operation=OP_PHONE_AUTH_REQUEST_CODE,
        destination_kind="phone",
        destination_normalized=destination,
        fingerprint=hash_value(destination),
        channel="sms",
        perform=perform,
    )
