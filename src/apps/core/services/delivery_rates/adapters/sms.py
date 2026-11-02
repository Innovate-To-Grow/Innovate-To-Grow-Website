"""AWS End User Messaging SMS SendTextMessage answers (``DELIVERY_RATES["signals"]["sms"]``).

The API quota is per account and Region, so a throttle stops every number of the Region (the cooldown group). AWS
names why it refused in the error's top-level ``Reason`` (botocore puts modeled error fields there): the monthly
spend limit stops all SMS until a probe (or a raised limit) shows it is clear; a disabled account or one without a
usable origination identity stops it until fixed.
"""

from botocore.exceptions import ClientError

from apps.core.models.base.delivery_rates import DeliveryChannel

from ..rules.defaults import channel_settings, signal_patterns
from ..rules.signals import RateSignal, Reason, blocked, code_in, none, throttle

# A stop AWS reports for the whole account: a configuration save cannot fix it, so only the timed probe re-checks.
ACCOUNT_BLOCKED = "account_blocked"


def sms_signal(exc: Exception) -> RateSignal | None:
    """The signal of a SendTextMessage error answer; None for a failure that is not one (a timeout, a lost
    connection)."""
    if not isinstance(exc, ClientError):
        return None
    response = exc.response or {}
    code = str(response.get("Error", {}).get("Code") or "")
    reason = str(response.get("Reason") or "")
    patterns = signal_patterns("sms")
    if code_in(code, patterns["throttle_codes"]):
        return throttle("throttled")
    if code_in(reason, patterns["spend_reasons"]):
        return blocked(Reason.SPEND_LIMIT, seconds=channel_settings(DeliveryChannel.SMS_SEND)["spend_probe_seconds"])
    if code_in(reason, patterns["blocked_reasons"]):
        return blocked(ACCOUNT_BLOCKED)
    if code_in(reason, patterns["config_blocked_reasons"]):
        # Not allowed to send from the configured identity: saving the AWS configuration probes at once.
        return blocked(Reason.PERMISSION)
    if code_in(code, patterns["message_codes"]) or code_in(reason, patterns["message_reasons"]):
        return none("message_rejected")
    return none("provider_error")
