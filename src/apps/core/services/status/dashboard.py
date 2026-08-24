"""Cache policy and UI envelope for the infrastructure status dashboard."""

from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .client import InternalStatusApiClient, StatusFetchError

logger = logging.getLogger(__name__)

FRESH_CACHE_TTL = 30
LAST_GOOD_CACHE_TTL = 15 * 60
NEGATIVE_CACHE_TTL = 10


def get_infrastructure_dashboard(*, force: bool = False, client=None, now=None) -> dict[str, Any]:
    """Return a stable UI envelope with fresh, stale, and unavailable states."""

    now = now or timezone.now()
    fresh_key, last_good_key, negative_key = _cache_keys()

    if not force:
        fresh = _cache_get(fresh_key)
        if _valid_record(fresh):
            return _available_envelope(fresh, now=now, cache_state="fresh")

        negative = _cache_get(negative_key)
        if _valid_failure(negative):
            return _failure_with_fallback(negative, last_good_key=last_good_key, now=now, cache_state="negative")

    status_client = client or InternalStatusApiClient()
    try:
        payload = status_client.fetch()
    except StatusFetchError as exc:
        failure = {"reason": exc.reason, "message": exc.public_message, "failedAt": now.isoformat()}
        _cache_delete(fresh_key)
        _cache_set(negative_key, failure, NEGATIVE_CACHE_TTL)
        return _failure_with_fallback(failure, last_good_key=last_good_key, now=now, cache_state="stale")
    except Exception:  # noqa: BLE001 -- injected/custom clients must not break the admin page.
        logger.error("Unexpected infrastructure status client failure")
        failure = {
            "reason": "error",
            "message": "Infrastructure status could not be loaded.",
            "failedAt": now.isoformat(),
        }
        _cache_delete(fresh_key)
        _cache_set(negative_key, failure, NEGATIVE_CACHE_TTL)
        return _failure_with_fallback(failure, last_good_key=last_good_key, now=now, cache_state="stale")

    record = {"status": payload, "fetchedAt": now.isoformat()}
    _cache_set(fresh_key, record, FRESH_CACHE_TTL)
    _cache_set(last_good_key, record, LAST_GOOD_CACHE_TTL)
    _cache_delete(negative_key)
    return _available_envelope(record, now=now, cache_state="refreshed")


def get_public_status_url() -> str:
    """Return only a safe HTTPS public-status URL for the external link."""

    value = str(getattr(settings, "STATUS_PUBLIC_URL", "") or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if not (
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    ):
        return ""
    return value


def _failure_with_fallback(failure, *, last_good_key: str, now, cache_state: str) -> dict[str, Any]:
    last_good = _cache_get(last_good_key)
    if _valid_record(last_good):
        envelope = _available_envelope(last_good, now=now, cache_state=cache_state)
        envelope.update(
            {
                "stale": True,
                "reason": failure["reason"],
                "message": failure["message"],
            }
        )
        return envelope
    return {
        "available": False,
        "stale": False,
        "reason": failure["reason"],
        "message": failure["message"],
        "fetchedAt": None,
        "staleAgeSeconds": None,
        "cacheState": "unavailable" if cache_state == "stale" else cache_state,
        "status": None,
    }


def _available_envelope(record, *, now, cache_state: str) -> dict[str, Any]:
    fetched_at = record["fetchedAt"]
    parsed = parse_datetime(fetched_at)
    try:
        stale_age = max(0, int((now - parsed).total_seconds())) if parsed else None
    except (TypeError, ValueError):
        # Treat malformed or timezone-naive cache metadata as unknown age instead
        # of allowing a damaged shared-cache value to break the admin page.
        stale_age = None
    return {
        "available": True,
        "stale": False,
        "reason": "",
        "message": "",
        "fetchedAt": fetched_at,
        "staleAgeSeconds": stale_age,
        "cacheState": cache_state,
        "status": deepcopy(record["status"]),
    }


def _cache_keys() -> tuple[str, str, str]:
    url = str(getattr(settings, "STATUS_INTERNAL_API_URL", "") or "")
    region = str(getattr(settings, "STATUS_API_REGION", "") or getattr(settings, "AWS_REGION", "") or "us-west-2")
    scope = hashlib.sha256(f"{region}|{url}".encode()).hexdigest()[:16]
    prefix = f"status:infrastructure:v1:{scope}"
    return f"{prefix}:fresh", f"{prefix}:last-good", f"{prefix}:negative"


def _valid_record(value) -> bool:
    return isinstance(value, dict) and isinstance(value.get("status"), dict) and isinstance(value.get("fetchedAt"), str)


def _valid_failure(value) -> bool:
    return isinstance(value, dict) and isinstance(value.get("reason"), str) and isinstance(value.get("message"), str)


def _cache_get(key):
    try:
        return cache.get(key)
    except Exception:  # noqa: BLE001 -- cache failure should fall through to the source.
        logger.error("Infrastructure status cache read failed")
        return None


def _cache_set(key, value, timeout):
    try:
        cache.set(key, value, timeout)
    except Exception:  # noqa: BLE001 -- the live response is still useful without cache.
        logger.error("Infrastructure status cache write failed")


def _cache_delete(key):
    try:
        cache.delete(key)
    except Exception:  # noqa: BLE001
        logger.error("Infrastructure status negative-cache cleanup failed")
