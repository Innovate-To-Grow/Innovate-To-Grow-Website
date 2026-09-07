from __future__ import annotations

import logging

from django.core.cache import cache

from apps.core.utils.client_ip import client_ip

from .config import SendVerificationSettings
from .exceptions import SendVerificationRateLimited, SendVerificationUnavailable

logger = logging.getLogger("apps.authn.send_verification")


def enforce_challenge_rate_limit(request, config: SendVerificationSettings) -> None:
    ip_address = client_ip(request) or "unknown"
    key = f"send-verification:challenge:{ip_address}"
    window = max(int(config.challenge_cache_window_seconds), 1)
    limit = max(int(config.challenge_cache_limit), 1)
    try:
        added = cache.add(key, 0, window)
        if not added and cache.get(key) is None:
            raise SendVerificationUnavailable("Shared throttling is unavailable.")
        count = cache.incr(key)
    except SendVerificationUnavailable:
        raise
    except Exception as exc:
        logger.exception("send verification challenge throttle failed")
        raise SendVerificationUnavailable("Shared throttling is unavailable.") from exc
    if count > limit:
        raise SendVerificationRateLimited(retry_after=window)
