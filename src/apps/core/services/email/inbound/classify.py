"""Telling automated mail from mail a person wrote, from headers and the first few KB of text only.

Pure functions: no database, no network. ``classify`` tries the classes in order and the first match wins: the
site's own message, bounce report, receipt, automatic reply (``autoreply``: vacation, left the organisation, other),
other system mail, list or bulk mail (``bulk``), spam, and otherwise human. Only strong signals (headers that mail
systems set, and the automatic-reply subject prefixes they write) put a message in an automated class. When unsure
the verdict is human, because a person's message hidden as automated costs more than an automated one shown:
content-only signs become hints on a human verdict (``possible_auto_reply``, ``possible_left_org``, …), never a class.

The caller says whether the message replies to an email the site sent (``Evidence.replies_to_site_mail``, from its
In-Reply-To and References). Such a reply is not list or bulk mail on weak bulk signals alone (a person answering a
campaign from a CRM tool), but an automatic reply stays one whatever it answers: the flag never makes automated mail
a person's. Every verdict on such a reply carries the hint ``replies_to_site_mail``.
"""

from dataclasses import dataclass, replace

from . import autoreply, bulk
from .bulk import spam_confidence_level
from .headers import first, joined
from .rules import (
    AUTH_RESULT_RE,
    AUTO_REPLY_HINT_RE,
    AUTOMATED,
    BOUNCE,
    BULK,
    CALENDAR_SUBJECT_RE,
    DKIM_PASS_DOMAIN_RE,
    EXCHANGE_RULE_HEADERS,
    HUMAN,
    LEFT_ORG_RE,
    OWN,
    QUARANTINE_LOCAL_RE,
    RECEIPT,
    RECEIPT_SUBJECT_RE,
    REPORT_SENDERS,
    SPAM,
    SYSTEM,
    SYSTEM_TEXT_RE,
    UNMONITORED_RE,
    VACATION_RE,
)

# How much of the decoded text the content rules read.
TEXT_HEAD_CHARS = autoreply.TEXT_HEAD_CHARS
REPLY_HINT = "replies_to_site_mail"
# A person's message that must never be answered automatically (RFC 3834: a list, a bulk sender, a request for none).
NO_AUTO_RESPONSE = "no_auto_response"


@dataclass(frozen=True)
class Evidence:
    """What the classifier reads of one message: its headers (lower-case names → raw values) and a few facts its
    parser (and the caller) found."""

    headers: dict
    from_address: str = ""
    from_name: str = ""
    subject: str = ""
    content_type: str = "text/plain"
    report_type: str = ""
    has_calendar: bool = False
    text_head: str = ""
    replies_to_site_mail: bool = False


@dataclass(frozen=True)
class Verdict:
    classification: str
    subtype: str = ""
    signals: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()
    # The address a left-the-organisation notice names instead of the one mailed, and how (``autoreply``): a hint
    # for staff, never verified and never applied.
    contact: str = ""
    contact_kind: str = ""

    @property
    def automated(self) -> bool:
        return self.classification in AUTOMATED


def classify(
    evidence: Evidence, *, own_addresses=frozenset(), scl_threshold: int = 5, bcl_threshold: int = 7
) -> Verdict:
    verdict = _decide(evidence, own_addresses, scl_threshold, bcl_threshold)
    if evidence.replies_to_site_mail and REPLY_HINT not in verdict.hints:
        verdict = replace(verdict, hints=(REPLY_HINT, *verdict.hints))
    return verdict


def _decide(evidence: Evidence, own_addresses, scl_threshold: int, bcl_threshold: int) -> Verdict:
    for check in (_own, _bounce, _receipt, _auto_reply, _system):
        verdict = check(evidence, own_addresses)
        if verdict is not None:
            return verdict
    found, overridden = bulk.detect(evidence, bcl_threshold=bcl_threshold)
    if found is not None:
        return Verdict(BULK, found.subtype, found.signals)
    spam = bulk.spam(evidence.headers, scl_threshold)
    if spam is not None:
        return Verdict(SPAM, spam.subtype, spam.signals)
    return Verdict(HUMAN, hints=_hints(evidence, own_addresses) + overridden)


def _local(address: str) -> str:
    return address.partition("@")[0]


def authenticated_as_own(evidence: Evidence, own_addresses) -> bool:
    """From one of the site's addresses and proven so: DKIM passed for its domain (or a parent), or Exchange marks it
    as internal (organization headers are stripped from mail arriving from outside)."""
    if evidence.from_address not in own_addresses:
        return False
    if first(evidence.headers, "x-ms-exchange-organization-authas").strip().lower() == "internal":
        return True
    domain = evidence.from_address.partition("@")[2]
    signed = DKIM_PASS_DOMAIN_RE.findall(joined(evidence.headers, "authentication-results"))
    return any(domain == item.lower() or domain.endswith("." + item.lower()) for item in signed)


def _own(evidence: Evidence, own_addresses) -> Verdict | None:
    return (
        Verdict(OWN, signals=("own_address_authenticated",)) if authenticated_as_own(evidence, own_addresses) else None
    )


def _bounce(evidence: Evidence, _own_addresses) -> Verdict | None:
    if evidence.content_type == "multipart/report" and evidence.report_type == "delivery-status":
        if RECEIPT_SUBJECT_RE.match(evidence.subject):
            return Verdict(RECEIPT, "delivery", ("delivery_status_report", "receipt_subject"))
        return Verdict(BOUNCE, signals=("delivery_status_report",))
    if first(evidence.headers, "x-failed-recipients"):
        return Verdict(BOUNCE, signals=("x_failed_recipients",))
    local = _local(evidence.from_address)
    if local in REPORT_SENDERS or local.startswith("microsoftexchange"):
        return Verdict(BOUNCE, signals=("report_sender",))
    return None


def _receipt(evidence: Evidence, _own_addresses) -> Verdict | None:
    if evidence.report_type == "disposition-notification":
        return Verdict(RECEIPT, "read", ("disposition_notification",))
    if evidence.content_type == "multipart/report" and RECEIPT_SUBJECT_RE.match(evidence.subject):
        return Verdict(RECEIPT, signals=("report", "receipt_subject"))
    return None


def _auto_reply(evidence: Evidence, own_addresses) -> Verdict | None:
    notice = autoreply.detect(evidence, own_addresses)
    if notice is None:
        return None
    return Verdict(notice.classification, notice.subtype, notice.signals, (), notice.contact, notice.contact_kind)


def _system(evidence: Evidence, _own_addresses) -> Verdict | None:
    if evidence.has_calendar and CALENDAR_SUBJECT_RE.match(evidence.subject):
        return Verdict(SYSTEM, "calendar", ("calendar_reply",))
    if QUARANTINE_LOCAL_RE.search(_local(evidence.from_address)):
        return Verdict(SYSTEM, "quarantine", ("quarantine_sender",))
    return None


def _hints(evidence: Evidence, own_addresses) -> tuple[str, ...]:
    content = f"{evidence.subject}\n{autoreply.own_text(evidence.text_head)}"
    headers = evidence.headers
    checks = (
        (NO_AUTO_RESPONSE, not autoreply.response_allowed(evidence)),
        ("possible_auto_reply", AUTO_REPLY_HINT_RE.search(evidence.subject) or VACATION_RE.search(content)),
        ("possible_left_org", LEFT_ORG_RE.search(content) or UNMONITORED_RE.search(content)),
        ("possible_receipt", RECEIPT_SUBJECT_RE.match(evidence.subject)),
        ("possible_system_mail", SYSTEM_TEXT_RE.search(content)),
        ("auto_response_suppress", "x-auto-response-suppress" in headers),
        ("null_return_path", first(headers, "return-path").strip() == "<>"),
        ("claims_own_address", evidence.from_address in own_addresses),
        ("exchange_rule_generated", any(name in headers for name in EXCHANGE_RULE_HEADERS)),
    )
    return tuple(name for name, found in checks if found)


def auth_summary(headers) -> dict:
    """SPF, DKIM, DMARC and composite-authentication results (the first of each), and Exchange's spam confidence and
    bulk complaint levels, for display."""
    summary: dict = {}
    for method, result in AUTH_RESULT_RE.findall(joined(headers, "authentication-results")):
        summary.setdefault(method.lower(), result.lower()[:16])
    for name, level in (("scl", spam_confidence_level(headers)), ("bcl", bulk.bulk_complaint_level(headers))):
        if level is not None:
            summary[name] = level
    return summary
