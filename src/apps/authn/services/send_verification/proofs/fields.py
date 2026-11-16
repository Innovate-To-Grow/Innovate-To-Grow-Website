"""The three proof fields a protected send request carries: the challenge id, the solved payload and the request id."""

from __future__ import annotations

from uuid import UUID

from ..rules.constants import FIELD_CHALLENGE_ID, FIELD_PAYLOAD, FIELD_REQUEST_ID


def _parse_uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def extract_verification_fields(data) -> tuple[UUID | None, str, UUID | None]:
    if hasattr(data, "get") and not isinstance(data, dict):
        try:
            data = {key: data.get(key) for key in (FIELD_CHALLENGE_ID, FIELD_PAYLOAD, FIELD_REQUEST_ID)}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return None, "", None
    challenge_id = _parse_uuid(data.get(FIELD_CHALLENGE_ID))
    payload = data.get(FIELD_PAYLOAD) or ""
    if not isinstance(payload, str):
        payload = str(payload)
    request_id = _parse_uuid(data.get(FIELD_REQUEST_ID))
    return challenge_id, payload.strip(), request_id
