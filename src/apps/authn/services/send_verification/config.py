from __future__ import annotations

import os
from dataclasses import dataclass, field

from django.conf import settings

from .constants import (
    ALGORITHM_PBKDF2_SHA256,
    ALLOWED_ALGORITHMS,
    ALLOWED_MODES,
    MODE_ENFORCE,
    MODE_OBSERVE,
    MODE_PAUSE,
)
from .exceptions import SendPaused, SendVerificationUnavailable


@dataclass(frozen=True)
class SendVerificationSettings:
    mode: str
    hmac_secret: str
    hmac_key_secret: str
    hmac_secret_previous: str
    hmac_key_secret_previous: str
    algorithm: str
    cost: int
    ttl_seconds: int
    max_payload_bytes: int
    destination_hourly_limit: int
    destination_cooldown_seconds: int
    sms_daily_limit: int | None
    idempotency_ttl_seconds: int
    retention_days: int
    challenge_cache_window_seconds: int
    challenge_cache_limit: int
    sources: dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    @property
    def hmac_secrets(self) -> tuple[str, ...]:
        secrets = [self.hmac_secret]
        if self.hmac_secret_previous and self.hmac_secret_previous != self.hmac_secret:
            secrets.append(self.hmac_secret_previous)
        return tuple(secret for secret in secrets if secret)

    @property
    def hmac_key_secrets(self) -> tuple[str, ...]:
        secrets = [self.hmac_key_secret]
        if self.hmac_key_secret_previous and self.hmac_key_secret_previous != self.hmac_key_secret:
            secrets.append(self.hmac_key_secret_previous)
        return tuple(secret for secret in secrets if secret)

    @property
    def requires_proof(self) -> bool:
        return self.mode == MODE_ENFORCE

    @property
    def is_paused(self) -> bool:
        return self.mode == MODE_PAUSE


def _integer(name: str, value, *, minimum: int = 1) -> int:
    # Do not silently clamp malformed policy or truncate floats into a weaker
    # limit. Environment values are intentionally parsed here, not at startup.
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise SendVerificationUnavailable(f"Invalid send verification setting: {name}.")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SendVerificationUnavailable(f"Invalid send verification setting: {name}.") from exc
    if result < minimum:
        raise SendVerificationUnavailable(f"Invalid send verification setting: {name}.")
    return result


def load_settings() -> SendVerificationSettings:
    from apps.core.models import SendVerificationConfig

    db = SendVerificationConfig.load()
    active = bool(db.pk and db.is_active)
    sources: dict[str, str] = {}

    def resolve(name: str, default, *, db_field: str | None = None):
        setting_name = f"SEND_VERIFICATION_{name.upper()}"
        override = getattr(settings, setting_name, None)
        if override is not None:
            origin = "Environment" if os.environ.get(setting_name) == override else "Django settings"
            sources[name] = f"{origin}: {setting_name}"
            return override
        if active and db_field:
            sources[name] = f"Active database configuration: {db_field}"
            return getattr(db, db_field)
        sources[name] = "Default"
        return default

    mode = str(resolve("mode", MODE_OBSERVE, db_field="mode")).strip().lower()
    # An active database pause must remain an emergency stop even when an
    # environment or test setting explicitly requests enforce/observe.
    if active and str(db.mode).strip().lower() == MODE_PAUSE:
        mode = MODE_PAUSE
        sources["mode"] = "Active database configuration: mode (pause takes precedence)"
    if mode not in ALLOWED_MODES:
        raise SendVerificationUnavailable("Invalid send verification setting: mode.")

    secrets = {}
    for name in ("hmac_secret", "hmac_key_secret", "hmac_secret_previous", "hmac_key_secret_previous"):
        value = resolve(name, "", db_field=name)
        if not isinstance(value, str):
            raise SendVerificationUnavailable(f"Invalid send verification setting: {name}.")
        secrets[name] = value.strip()

    algorithm = str(resolve("algorithm", ALGORITHM_PBKDF2_SHA256, db_field="algorithm")).strip()
    if algorithm not in ALLOWED_ALGORITHMS:
        raise SendVerificationUnavailable("Invalid send verification setting: algorithm.")

    sms_daily = resolve("sms_daily_limit", None, db_field="sms_daily_limit")
    if sms_daily is not None:
        # Zero explicitly clears the cap. It never means unlimited SMS:
        # require_ready() refuses protected SMS in enforce mode until calibrated.
        sms_daily = _integer("sms_daily_limit", sms_daily, minimum=0) or None

    def integer(name: str, default: int, *, db_field: str | None = None, minimum: int = 1):
        return _integer(name, resolve(name, default, db_field=db_field), minimum=minimum)

    return SendVerificationSettings(
        mode=mode,
        **secrets,
        algorithm=algorithm,
        cost=integer("cost", 5000, db_field="cost"),
        ttl_seconds=integer("ttl_seconds", 300, db_field="challenge_ttl_seconds", minimum=30),
        max_payload_bytes=integer("max_payload_bytes", 8192),
        destination_hourly_limit=integer("destination_hourly_limit", 10, db_field="destination_hourly_limit"),
        destination_cooldown_seconds=integer(
            "destination_cooldown_seconds", 60, db_field="destination_cooldown_seconds", minimum=0
        ),
        sms_daily_limit=sms_daily,
        idempotency_ttl_seconds=integer("idempotency_ttl_seconds", 86400),
        retention_days=integer("retention_days", 14),
        challenge_cache_window_seconds=integer("challenge_cache_window_seconds", 60),
        challenge_cache_limit=integer("challenge_cache_limit", 30),
        sources=sources,
    )


def require_ready(*, for_sms: bool = False) -> SendVerificationSettings:
    config = load_settings()
    if config.is_paused:
        raise SendPaused()
    if not config.hmac_secret:
        raise SendVerificationUnavailable("Send verification is not configured.")
    if for_sms and config.mode == MODE_ENFORCE and not config.sms_daily_limit:
        raise SendVerificationUnavailable("SMS sending is paused until a daily reservation limit is configured.")
    return config
