"""Classifying one recipient of a bounce report: its **category** (what went wrong), the coarse **classification**
derived from it (hard, soft, rejected, delayed, unknown), whether the address itself will not work, a short reason, and
the SMTP reply code.

The SMTP reply code (``550``) and the enhanced status code (``5.1.1``, RFC 3463) decide; the diagnostic text only
refines a generic code (``rules``). When the report's own status is generic (``5.0.0``) but its diagnostic quotes the
receiving server's specific code of the same class (``550 5.1.1 ...``), that code decides.

- ``delayed`` action: delivery delayed, the server keeps retrying; never a failure yet.
- Evidence against the address: only ``hard`` (it does not exist) and ``mailbox_disabled``.
- Temporary: ``transient`` (connection, DNS, timeouts, expiry after retries, a message too large, every other
  ``4.x.x``) and ``mailbox_full``. The address is probably fine.
- Our sending side: ``spam_rejected`` (spam, block lists, reputation, sender authentication) and ``relay_denied``
  (the route or authorisation of our sending); ``policy_rejected`` is the recipient server's own rules.
- ``unknown``: no code, or a generic or unrecognised code with no recognisable reason (a bare ``5.0.0``).
"""

import re
from dataclasses import dataclass

from apps.core.models import EmailBounce

from .dsn import STATUS_RE
from .rules import codes, phrases
from .rules.codes import reason

Classification = EmailBounce.Classification
Category = EmailBounce.Category
COARSE = {
    Category.HARD: Classification.HARD,
    Category.MAILBOX_DISABLED: Classification.HARD,
    Category.MAILBOX_FULL: Classification.SOFT,
    Category.TRANSIENT: Classification.SOFT,
    Category.SPAM_REJECTED: Classification.REJECTED,
    Category.RELAY_DENIED: Classification.REJECTED,
    Category.POLICY_REJECTED: Classification.REJECTED,
    Category.DELAYED: Classification.DELAYED,
    Category.UNKNOWN: Classification.UNKNOWN,
}
# ``is_permanent``: whether the address itself will not work (False for the rest; unknown when the report is unclear).
ADDRESS_FAILS = {Category.HARD: True, Category.MAILBOX_DISABLED: True, Category.UNKNOWN: None}
DEFAULT_REASONS = {
    Category.HARD: "Recipient address does not exist",
    Category.MAILBOX_DISABLED: "Recipient mailbox is disabled",
    Category.MAILBOX_FULL: "Recipient mailbox is full",
    Category.TRANSIENT: "Temporary failure",
    Category.SPAM_REJECTED: "Rejected as spam, or for our sending reputation or authentication",
    Category.RELAY_DENIED: "Relay denied",
    Category.POLICY_REJECTED: "Rejected by the recipient's server policy",
    Category.UNKNOWN: "Delivery failed; the report does not say why",
}
_NOT_FAILURES = frozenset({"delivered", "relayed", "expanded"})
# The reply code a diagnostic starts with ("550 5.1.1 ...", "554-5.7.1 ..."), else one followed by an enhanced code.
_SMTP_START_RE = re.compile(r"^\s*([245]\d\d)(?![\d.])")
_SMTP_PAIR_RE = re.compile(r"(?<![\d.])([245]\d\d)[ -]+[245]\.\d{1,3}\.\d{1,3}(?![\d.])")
_SPACE_RE = re.compile(r"\s+")
TEXT_LIMIT = 1000


@dataclass(frozen=True)
class Verdict:
    classification: str
    category: str
    is_permanent: bool | None
    reason: str
    smtp_code: str = ""


def smtp_code(diagnostic: str) -> str:
    """The SMTP reply code of a diagnostic, or ""."""
    text = str(diagnostic or "")[:TEXT_LIMIT]
    match = _SMTP_START_RE.match(text) or _SMTP_PAIR_RE.search(text)
    return match.group(1) if match else ""


def _parts(code: str) -> tuple[int, int, int] | None:
    pieces = str(code or "").split(".")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        return None
    return int(pieces[0]), int(pieces[1]), int(pieces[2])


def effective_status(status: str, diagnostic: str) -> str:
    """``status``, or, when it is generic, the first specific code of the same class the diagnostic quotes."""
    parts = _parts(status)
    if parts is not None and not codes.is_generic(*parts):
        return status
    for match in STATUS_RE.finditer(str(diagnostic or "")[:TEXT_LIMIT]):
        found = _parts(".".join(match.groups()))
        if found[0] in (4, 5) and (parts is None or found[0] == parts[0]) and not codes.is_generic(*found):
            return ".".join(match.groups())
    return status


def _refined(text: str, allowed, default: str) -> tuple[str, str]:
    phrase = phrases.refine(text, allowed)
    return (phrase.category, phrase.reason) if phrase is not None else (default, "")


def _decide(status: str, smtp: str, text: str) -> tuple[str, str]:
    """The category, and the reason of the phrase that decided it ("" when a code did)."""
    parts = _parts(status)
    if parts is None:
        if smtp.startswith("4"):
            return _refined(text, phrases.TEMPORARY_REFINEMENTS, Category.TRANSIENT)
        return _refined(text, phrases.ALL, Category.UNKNOWN)
    if status in codes.SIZE_CODES and phrases.ZERO_LIMIT_RE.search(text):
        return Category.MAILBOX_DISABLED, phrases.ZERO_LIMIT.reason
    found = codes.specific(*parts)
    if status in codes.AMBIGUOUS:
        return _refined(text, phrases.AMBIGUOUS_REFINEMENTS, found)
    if found is not None:
        return found, ""
    category = codes.default(*parts)
    if not codes.is_generic(*parts):
        return category, ""
    if parts[0] == 4:
        return _refined(text, phrases.TEMPORARY_REFINEMENTS, category)
    return _refined(text, phrases.POLICY_REFINEMENTS if parts[1] == 7 else phrases.ALL, category)


def _reason(status: str, text: str, category: str) -> str:
    """The code's own reason, else the reason of a phrase of the same category, else the category's or the code
    subject's."""
    if status in codes.REASONS:
        return codes.REASONS[status]
    phrase = phrases.refine(text, {category})
    if phrase is not None:
        return phrase.reason
    parts = _parts(status)
    if parts is None or codes.is_generic(*parts) or codes.specific(*parts) is not None:
        return DEFAULT_REASONS[category]
    return reason(status)


def categorize(status: str, smtp: str, text: str) -> tuple[str, str]:
    """``(category, reason)`` of a failed recipient from its enhanced status code (or ""), its SMTP reply code (or "")
    and its lower-case, whitespace-collapsed diagnostic."""
    if not (status or smtp or text):
        return Category.UNKNOWN, "The report gives no status code"
    category, why = _decide(status, smtp, text)
    return category, why or _reason(status, text, category)


def classify(action: str, status: str, diagnostic: str = "") -> Verdict | None:
    """The verdict for one recipient, or None when the report says the message went through (not a failure)."""
    action = str(action or "").strip().lower()
    status = str(status or "")
    if action in _NOT_FAILURES or status.startswith("2."):
        return None
    diagnostic = str(diagnostic or "")[:TEXT_LIMIT]
    smtp = smtp_code(diagnostic)
    if action == "delayed":
        why = reason(status) or "Delivery delayed; the server keeps retrying"
        return Verdict(Classification.DELAYED, Category.DELAYED, False, why, smtp)
    category, why = categorize(effective_status(status, diagnostic), smtp, _SPACE_RE.sub(" ", diagnostic).lower())
    return Verdict(COARSE[category], category, ADDRESS_FAILS.get(category, False), why, smtp)
