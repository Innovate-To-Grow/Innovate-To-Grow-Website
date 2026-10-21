from __future__ import annotations

import base64
import json
import logging

from .config import SendVerificationSettings
from .constants import ALLOWED_ALGORITHMS
from .exceptions import SendVerificationContextMismatch, SendVerificationExpired, SendVerificationInvalid

logger = logging.getLogger("apps.authn.send_verification")


def parse_payload_dict(payload: str) -> dict:
    try:
        raw = base64.b64decode(payload, validate=True)
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SendVerificationInvalid() from exc
    if not isinstance(parsed, dict):
        raise SendVerificationInvalid()
    return parsed


def payload_parameters(payload: str) -> dict:
    parsed = parse_payload_dict(payload)
    challenge = parsed.get("challenge") if isinstance(parsed.get("challenge"), dict) else parsed
    parameters = challenge.get("parameters") if isinstance(challenge, dict) else None
    return parameters if isinstance(parameters, dict) else {}


def verify_payload(payload: str, config: SendVerificationSettings, *, algorithm=None, cost=None) -> None:
    if not payload or not isinstance(payload, str):
        raise SendVerificationInvalid()
    if len(payload.encode("utf-8")) > config.max_payload_bytes:
        raise SendVerificationInvalid("Verification payload is too large.")

    _check_parameters(
        payload_parameters(payload),
        expected_algorithm=algorithm or config.algorithm,
        expected_cost=config.cost if cost is None else cost,
    )
    _verify_with_current_or_previous_secrets(payload, config)


def _check_parameters(parameters: dict, *, expected_algorithm, expected_cost) -> None:
    supplied_algorithm = parameters.get("algorithm")
    supplied_cost = parameters.get("cost")
    if (
        not isinstance(supplied_algorithm, str)
        or supplied_algorithm not in ALLOWED_ALGORITHMS
        or supplied_algorithm != expected_algorithm
    ):
        raise SendVerificationInvalid()
    # JSON booleans and coercible strings/floats are not valid integer costs.
    if type(supplied_cost) is not int or supplied_cost <= 0 or supplied_cost != expected_cost:
        raise SendVerificationInvalid()


def _verify_with_current_or_previous_secrets(payload: str, config: SendVerificationSettings) -> None:
    from altcha import verify_solution

    last_error = None
    key_secrets = config.hmac_key_secrets or (None,)
    for hmac_secret in config.hmac_secrets:
        for key_secret in key_secrets:
            try:
                result = verify_solution(
                    payload,
                    hmac_secret,
                    hmac_key_secret=key_secret,
                )
            except Exception as exc:  # noqa: BLE001 - library parse failures are invalid proofs
                last_error = exc
                continue
            if result.expired:
                raise SendVerificationExpired()
            if result.verified:
                return
            last_error = result
    logger.info("send_verification.proof_invalid")
    if last_error is not None and getattr(last_error, "expired", False):
        raise SendVerificationExpired()
    raise SendVerificationInvalid()


def check_signed_challenge(payload: str, challenge, *, operation: str) -> None:
    """The verified proof must be signed for this challenge and operation."""
    signed_data = payload_parameters(payload).get("data") or {}
    if not isinstance(signed_data, dict):
        raise SendVerificationInvalid()
    if str(signed_data.get("challenge_id") or "") != str(challenge.id):
        raise SendVerificationContextMismatch()
    if str(signed_data.get("operation") or "") != operation:
        raise SendVerificationContextMismatch()
