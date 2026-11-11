"""Classifying one recipient of a bounce report: hard, soft, rejected, delayed or unknown; whether the failure is
permanent; and a short reason. Everything comes from the DSN action and the enhanced status code (RFC 3463).

- ``delayed`` action: delivery delayed (the server keeps retrying), never a failure yet.
- ``5.7.x``: rejected by the recipient's security or policy (spam filtering, blocking, authorisation).
- other ``5.x.x``: a hard bounce, except the conditions that pass (a full mailbox, a message too large, a delivery
  that expired after retries, content conversion): soft bounces, as mail services usually class them.
- ``4.x.x`` with a failed action: the server gave up on a temporary failure, a soft bounce.
- no status code: unknown delivery status.
"""

from dataclasses import dataclass

from apps.core.models import EmailBounce

Classification = EmailBounce.Classification

_REASONS = {
    "5.1.0": "Bad recipient address",
    "5.1.1": "Recipient mailbox does not exist",
    "5.1.2": "Recipient domain does not exist",
    "5.1.3": "Invalid recipient address",
    "5.1.6": "Recipient mailbox has moved",
    "5.1.10": "Recipient not found",
    "5.2.1": "Recipient mailbox is disabled",
    "5.2.2": "Recipient mailbox is full",
    "5.2.3": "Message too large for the recipient",
    "5.3.4": "Message too large",
    "5.4.1": "Recipient address rejected (access denied)",
    "5.4.4": "Recipient domain cannot be reached",
    "5.4.6": "Mail routing loop",
    "5.4.7": "Delivery expired",
    "5.4.300": "Delivery expired",
    "4.4.7": "Delivery expired",
    "5.7.1": "Rejected by the recipient's server policy",
    "5.7.23": "Rejected: sender authentication (SPF) failed",
    "5.7.26": "Rejected: sender authentication (DMARC) failed",
    "5.7.509": "Rejected: sender authentication (DMARC) failed",
    "5.7.606": "Rejected: sending server is blocked",
    "5.7.708": "Rejected: sending server is not trusted",
}
_SUBJECT_REASONS = {
    "1": "Recipient address problem",
    "2": "Recipient mailbox problem",
    "3": "Recipient mail system problem",
    "4": "Network or routing problem",
    "5": "Mail protocol problem",
    "6": "Message content problem",
    "7": "Rejected by security or policy",
}
_SOFT_PERMANENT = frozenset({"5.2.2", "5.2.3", "5.3.4", "5.4.6", "5.4.7", "5.4.300"})
_NOT_FAILURES = frozenset({"delivered", "relayed", "expanded"})


@dataclass(frozen=True)
class Verdict:
    classification: str
    is_permanent: bool | None
    reason: str


def reason(status: str) -> str:
    if status in _REASONS:
        return _REASONS[status]
    parts = status.split(".")
    if len(parts) != 3:
        return ""
    base = _SUBJECT_REASONS.get(parts[1], "Delivery failure")
    return f"Temporary: {base.lower()}" if parts[0] == "4" else base


def classify(action: str, status: str) -> Verdict | None:
    """The verdict for one recipient, or None when the report says the message went through (not a failure)."""
    action = str(action or "").strip().lower()
    if action in _NOT_FAILURES or status.startswith("2."):
        return None
    if action == "delayed":
        return Verdict(Classification.DELAYED, False, reason(status) or "Delivery delayed; the server keeps retrying")
    if not status:
        return Verdict(Classification.UNKNOWN, None, "The report gives no status code")
    klass, subject = status.split(".")[:2]
    if klass == "4":
        return Verdict(Classification.SOFT, False, reason(status))
    if subject == "7":
        return Verdict(Classification.REJECTED, True, reason(status))
    if status in _SOFT_PERMANENT or subject in ("3", "6"):
        return Verdict(Classification.SOFT, True, reason(status))
    return Verdict(Classification.HARD, True, reason(status))
