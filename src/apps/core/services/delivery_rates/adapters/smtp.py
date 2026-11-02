"""SMTP reply codes and texts (``DELIVERY_RATES["signals"]["smtp"]``), Gmail SMTP and the Workspace relay included.

Google reuses reply codes for different limits, so the code, the enhanced status and the text are matched together.
"""

from apps.core.models.base.delivery_rates import DeliveryChannel

from ..rules.defaults import channel_settings, signal_patterns
from ..rules.signals import RateSignal, Reason, blocked, none, pause, quota, text_has, throttle


def smtp_signal(code: int, text: str) -> RateSignal:
    """The signal of an SMTP reply (``code`` and its text, enhanced status first, as the server sent it)."""
    patterns = signal_patterns("smtp")
    line = f"{code} {text}"
    if code in patterns["auth_blocked_statuses"]:
        return blocked(Reason.AUTH)
    if text_has(line, patterns["pause_texts"]):
        seconds = channel_settings(DeliveryChannel.SMTP_SEND)["sign_in_pause_seconds"]
        return pause("sign_in_attempts", seconds=seconds)
    if text_has(line, patterns["quota_texts"]):
        return quota("daily_limit")
    if text_has(line, patterns["message_texts"]):
        return none("recipient_rate")
    if text_has(line, patterns["throttle_texts"]):
        return throttle("throttled")
    return none("rejected")


def reply_text(raw) -> str:
    """An smtplib reply (bytes) as text for matching."""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw or "")
