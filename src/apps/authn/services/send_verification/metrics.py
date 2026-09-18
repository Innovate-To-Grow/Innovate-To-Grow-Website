from __future__ import annotations

import logging
import unicodedata

from .hashing import short_destination_hash

logger = logging.getLogger("apps.authn.send_verification")


def _log_token(value: object) -> str:
    """Keep untrusted values within one token of one physical log record."""
    text = str(value).replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")
    return "".join(
        f"\\u{ord(char):04x}" if char.isspace() or unicodedata.category(char).startswith("C") or char == "=" else char
        for char in text
    )


def emit(event: str, **fields) -> None:
    destination = fields.pop("destination", None)
    if destination:
        fields["destination_hash"] = short_destination_hash(str(destination))
    payload = " ".join(
        f"{_log_token(key)}={_log_token(value)}" for key, value in sorted(fields.items()) if value is not None
    )
    logger.info("send_verification.%s %s", _log_token(event), payload)
