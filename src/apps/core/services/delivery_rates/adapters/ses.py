"""Amazon SES SendRawEmail answers (``DELIVERY_RATES["signals"]["ses"]``)."""

from botocore.exceptions import ClientError

from apps.core.models.base.delivery_rates import DeliveryChannel

from ..rules.defaults import channel_settings, signal_patterns
from ..rules.signals import RateSignal, Reason, Scope, blocked, code_in, none, quota, text_has, throttle


def ses_signal(exc: Exception) -> RateSignal | None:
    """The signal of an SES error answer; None for a failure that is not one (a timeout, a lost connection)."""
    if not isinstance(exc, ClientError):
        return None
    error = (exc.response or {}).get("Error", {})
    code, text = str(error.get("Code") or ""), str(error.get("Message") or "")
    patterns = signal_patterns("ses")
    # SES answers both "Daily message quota exceeded" and "Maximum sending rate exceeded" as Throttling.
    if text_has(text, patterns["quota_texts"]):
        return quota("daily_quota", seconds=channel_settings(DeliveryChannel.SES_SEND)["quota_recheck_seconds"])
    if code_in(code, patterns["throttle_codes"]) or text_has(text, patterns["throttle_texts"]):
        return throttle("throttled")
    if code_in(code, patterns["blocked_codes"]):
        return blocked(Reason.ACCOUNT_PAUSED)
    if code_in(code, patterns["bulk_blocked_codes"]):
        return blocked("configuration_set_paused", scope=Scope.BULK)
    if code_in(code, patterns["message_codes"]):
        return none("message_rejected")
    return none("provider_error")
