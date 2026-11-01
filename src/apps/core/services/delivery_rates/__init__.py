"""Delivery-rate control for every delivery channel: Microsoft Graph send and read, Amazon SES, SMTP, Gmail IMAP,
the Gmail API and AWS SMS.

Each channel has one ``DeliveryRatePolicy`` (Mail → Delivery Rates: the Smart rate switch, the manual rate and the
provider limits) and a ``DeliveryRateState`` per identity. A sender wraps each provider call::

    admission = admit(channel, identity, lane=Lane.BULK, budget_cost=recipients, message_cost=1)
    try:
        response = provider_call()
    except ProviderError as exc:
        record(admission, adapter_signal(exc))
        raise
    record(admission, ok())

or uses ``controlled(...)`` for the same. ``RateDeferred`` means "certainly not sent, try at ``until``".

- ``rules``: the pure rules. ``rules.policy.effective_rate`` is the only home of the precedence rule.
- ``runtime``: admission, feedback, budgets, breakers and discovery on the state rows.
- ``snapshot`` / ``status_text``: the status lines; ``receivers``: config saves half-open breakers.
- ``families``: the active channel of each family (email, SMS), the worker's lane gates and inline batch sizes;
  ``maintenance``: the worker's periodic limit reads and purges.
"""

from .families import Target, active_target, inline_batch_limit, lane_gated, register_family
from .maintenance import run_maintenance
from .rules.channels import (
    Family,
    Lane,
    channel_info,
    cooldown_group,
    external_recipients,
    imap_identity,
    mailbox_identity,
    ses_identity,
    sms_identity,
    smtp_identity,
)
from .rules.signals import (
    RateSignal,
    Reason,
    Scope,
    SignalKind,
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
from .rules.sms_parts import sms_parts
from .runtime.admission import Admission, Costs, RateDeferred, RateRefused
from .runtime.breaker import resume
from .runtime.context import WaitMode, wait_cap, wait_mode
from .runtime.discovery import refresh_discovery
from .runtime.feedback import controlled, record, release, reset_smart
from .runtime.limiter import admit
from .runtime.state import AdmissionInTransaction
from .snapshot import ChannelStatus, IdentityStatus, channel_status, snapshot

__all__ = [
    "Admission",
    "AdmissionInTransaction",
    "ChannelStatus",
    "Costs",
    "Family",
    "IdentityStatus",
    "Lane",
    "RateDeferred",
    "RateRefused",
    "RateSignal",
    "Reason",
    "Scope",
    "SignalKind",
    "Target",
    "WaitMode",
    "active_target",
    "admit",
    "blocked",
    "channel_info",
    "channel_status",
    "code_in",
    "controlled",
    "cooldown_group",
    "external_recipients",
    "imap_identity",
    "inline_batch_limit",
    "lane_gated",
    "mailbox_identity",
    "none",
    "ok",
    "parse_retry_after",
    "pause",
    "quota",
    "record",
    "refresh_discovery",
    "register_family",
    "release",
    "reset_smart",
    "resume",
    "run_maintenance",
    "ses_identity",
    "sms_identity",
    "sms_parts",
    "smtp_identity",
    "snapshot",
    "text_has",
    "throttle",
    "uncertain",
    "wait_cap",
    "wait_mode",
]
