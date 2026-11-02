"""Gmail API answers (``DELIVERY_RATES["signals"]["gmail_api"]``): ``messages.send``, the token endpoint and the key store.

The Gmail API reports no quota or remaining usage, so the limits are the documented seeds and Smart rate reacts
only to these answers. Each one is about the impersonated account (the channel identity); its cooldown group is
not shared with Gmail IMAP, whose bandwidth limits are "equal to, but independent of" the API's. Reasons are read
from the legacy ``errors[0].reason``, an ErrorInfo ``reason`` or ``error.status``; the message text is only matched.
"""

import re
from datetime import UTC, datetime

from django.utils import timezone

from apps.core.models.base.delivery_rates import DeliveryChannel

from ..rules.defaults import channel_settings, signal_patterns
from ..rules.signals import (
    RateSignal,
    Reason,
    blocked,
    code_in,
    none,
    ok,
    parse_retry_after,
    pause,
    quota,
    text_has,
    throttle,
    uncertain,
)

# Google's errors guide says only that a mail-sending 429 comes "with a retry time"; the form seen in practice is
# "Retry after <RFC 3339 timestamp>" inside the message.
_RETRY_AFTER_TEXT = re.compile(r"Retry after (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?Z")
_REQUEST_TIMEOUT = 408
_PAYLOAD_TOO_LARGE = 413


def retry_after(headers: dict, message: str = "") -> float | None:
    """A Retry-After header (delta-seconds or an HTTP-date), else a "Retry after <timestamp>" in the message, in
    seconds clamped to [1, ``controller.retry_after_max_seconds``]; None when neither is there."""
    seconds = parse_retry_after(headers.get("retry-after"))
    if seconds is not None:
        return seconds
    match = _RETRY_AFTER_TEXT.search(str(message or ""))
    if not match:
        return None
    try:
        when = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parse_retry_after(max(0.0, (when - timezone.now()).total_seconds()))


def send_signal(status: int, headers: dict, reason: str, message: str, *, fresh_token: bool = False) -> RateSignal:
    """The signal of one ``messages.send`` answer (``reason``: the allow-listed error reason, or "")."""
    patterns = signal_patterns("gmail_api")
    limits = channel_settings(DeliveryChannel.GMAIL_API_SEND)
    if status == 200:
        return ok()
    if status == 429:
        return _too_many_requests(headers, message, patterns, limits)
    if code_in(reason, patterns["daily_quota_reasons"]):
        return quota("project_quota", seconds=limits["daily_quota_recheck_seconds"])
    if code_in(reason, patterns["throttle_reasons"]) or status in patterns["throttle_statuses"]:
        return throttle("throttled", retry_after=retry_after(headers, message))
    if status == 401:
        # An expired cached token is refreshed on the next send; a fresh one refused means the grant is gone.
        return blocked(Reason.AUTH) if fresh_token else none("token_rejected")
    if code_in(reason, patterns["blocked_reasons"]) or status == 404:
        return blocked(Reason.PERMISSION)
    if status == 403:
        return blocked(Reason.AUTH)
    if code_in(reason, patterns["message_reasons"]) or status in (400, _PAYLOAD_TOO_LARGE) or 400 <= status < 500:
        return none("rejected")
    return uncertain("server_error")


def _too_many_requests(headers: dict, message: str, patterns: dict, limits: dict) -> RateSignal:
    wait = retry_after(headers, message)
    if text_has(message, patterns["mail_sending_texts"]):
        # The account's daily sending limit: Google may refuse for "multiple hours", users for up to 24 hours.
        return quota("daily_sending_limit", seconds=wait)
    if text_has(message, patterns["concurrent_texts"]):
        return throttle("concurrent_requests", retry_after=wait or limits["concurrent_throttle_seconds"])
    if text_has(message, patterns["bandwidth_texts"]):
        return quota("bandwidth", seconds=wait or limits["bandwidth_breaker_seconds"])
    return throttle("throttled", retry_after=wait)


def token_signal(status: int, headers: dict, code: str) -> RateSignal:
    """A failed token request: busy (pause the account and back off), or the delegation, key or account refused
    (a breaker until the configuration is saved, or a timed probe). No mail was sent either way."""
    patterns = signal_patterns("gmail_api")
    if text_has(code, patterns["token_pause_codes"]) or status in (_REQUEST_TIMEOUT, 429) or status >= 500:
        return pause("token_endpoint", retry_after=retry_after(headers))
    return blocked(Reason.AUTH)


def store_signal(*, transient: bool) -> RateSignal:
    """The key could not be read: the store is busy (pause and back off), or the key is gone or refused."""
    return pause("credential_store") if transient else blocked(Reason.AUTH)
