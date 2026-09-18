from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.utils.crypto import salted_hmac


def hash_value(value: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:{value}".encode()).hexdigest()


def short_destination_hash(value: str) -> str:
    # Destinations are guessable; a public digest permits offline enumeration.
    return salted_hmac("send-verification.destination-log", value, algorithm="sha256").hexdigest()[:12]


def fingerprint_payload(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
