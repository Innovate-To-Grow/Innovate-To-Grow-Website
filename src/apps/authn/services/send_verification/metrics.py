from __future__ import annotations

import logging

from .hashing import short_destination_hash

logger = logging.getLogger("apps.authn.send_verification")


def emit(event: str, **fields) -> None:
    destination = fields.pop("destination", None)
    if destination:
        fields["destination_hash"] = short_destination_hash(str(destination))
    payload = " ".join(f"{key}={value}" for key, value in sorted(fields.items()) if value is not None)
    logger.info("send_verification.%s %s", event, payload)
