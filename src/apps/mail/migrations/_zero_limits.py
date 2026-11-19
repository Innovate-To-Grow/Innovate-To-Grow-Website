"""Frozen 0029 data correction, also used to reconcile late writes from the preceding worker image."""

import re
from email.utils import parseaddr
from importlib import import_module

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

previous = import_module("apps.core.migrations.0047_email_bounce_category")
ZERO_REASON = "Recipient mailbox reports a 0 KB limit; retry after the receiving service is fixed"
ZERO_SIZE = re.compile(
    r"\b(?:max(?:imum)?|limit|allowed)\b[^0-9.;]{0,40}?(?<![\d.])0(?:\.0+)? ?(?:[kmg]i?b|bytes?|k)\b"
)
SEVERITY = {"hard": 4, "rejected": 3, "soft": 2, "unknown": 1, "delayed": 0}


ROUTING_REASONS = {
    "5.4.1": "The report does not establish why the destination host was unavailable",
    "5.4.4": "The report does not establish why routing failed",
}


def _ambiguous_verdict(status, text):
    sender = previous.refine(text, {"relay_denied", "spam_rejected"})
    missing = previous.refine(text, {"hard"})
    if sender and missing:
        return ("unknown", "unknown", None, "Conflicting sending-side and recipient diagnostics; review the report")
    if sender:
        return ("rejected", sender[0], False, sender[1])
    if ZERO_SIZE.search(text):
        if missing:
            return ("hard", missing[0], True, missing[1])
        return ("soft", "transient", False, ZERO_REASON)
    temporary = previous.refine(text, {"transient"})
    if temporary:
        return ("soft", temporary[0], False, temporary[1])
    if re.search(r"\bno answer from host\b", text):
        return ("soft", "transient", False, "Could not connect to the recipient's mail server")
    if status in ROUTING_REASONS:
        if missing:
            return ("hard", missing[0], True, missing[1])
        if status == "5.4.1" and "recipient address rejected: access denied" in text:
            return ("hard", "hard", True, "Exchange rejected the recipient address (access denied)")
        return ("unknown", "unknown", None, ROUTING_REASONS[status])
    return None


def corrected_verdict(report, reverse, modern):
    if modern:
        status = previous.effective_status(report.status_code, report.diagnostic_code)
        text = " ".join(report.diagnostic_code[:1000].lower().split())
        if status in previous.AMBIGUOUS:
            verdict = _ambiguous_verdict(status, text)
            if verdict:
                return verdict
        # Earlier revisions let a 0 KB phrase override other phrases on generic reports.
        if report.category == "transient" and report.reason == ZERO_REASON and ZERO_SIZE.search(text):
            old = previous.classify(report.action, report.status_code, text)
            if old and old[1] in ("relay_denied", "spam_rejected", "hard"):
                return old[:4]
    return zero_verdict(report, reverse)


def zero_verdict(report, reverse):
    text = " ".join(report.diagnostic_code[:1000].lower().split())
    if not ZERO_SIZE.search(text):
        return None
    old = previous.classify(report.action, report.status_code, text)
    if not old or old[0] == "delayed":
        return None
    if reverse:
        # Reports can also be *created* by the new image after the forward migration.
        # Its public reason is not provenance. Restore the old rule for this particular DSN.
        return old[:4]
    status = previous.effective_status(report.status_code, text)
    if status.startswith("5.7."):
        return None
    if old[1] in ("spam_rejected", "relay_denied", "policy_rejected", "hard"):
        return None
    return ("soft", "transient", False, ZERO_REASON)


def _adjust_aggregate(Address, report, state, old, new, db):
    if state.cursor_at is None or report.created_at > state.cursor_at:
        return
    if report.created_at == state.cursor_at and (state.cursor_id is None or report.pk > state.cursor_id):
        return
    address = parseaddr(report.recipient)[1].strip().lower()
    row = Address.objects.using(db).select_for_update().filter(address=address).first()
    if row is None or not row.graph_last_at:
        return
    counts = dict(row.category_counts or {})
    if counts.get(old[1], 0) == 0:
        return
    changed = set()
    if old[1] != new[1]:
        counts[old[1]] -= 1
        if not counts[old[1]]:
            del counts[old[1]]
        counts[new[1]] = counts.get(new[1], 0) + 1
        row.category_counts = counts
        changed.add("category_counts")
    if old[0] != new[0]:
        for kind, delta in ((old[0], -1), (new[0], 1)):
            field = f"{kind}_count"
            setattr(row, field, max(0, getattr(row, field) + delta))
            changed.add(field)
    if (
        row.graph_last_at == report.received_at
        and row.last_category == old[1]
        and row.last_status_code == report.status_code
    ):
        row.last_classification, row.last_category, row.last_reason = new[0], new[1], new[3]
        changed.update(("last_classification", "last_category", "last_reason"))
    # Refresh will compute the current suggestion. Do not keep an obsolete recommendation to replace this address.
    if (row.suggestion == "replace" and not counts.get("mailbox_disabled")) or (
        row.suggestion == "undeliverable" and not counts.get("hard") and not row.ses_permanent_count
    ):
        row.suggestion = ""
        changed.add("suggestion")
    if changed:
        row.save(using=db, update_fields=sorted(changed))


def reconcile(apps, db, *, reverse=False, state=None, modern=False, scope=None):
    Bounce = apps.get_model("core", "EmailBounce")
    Address = apps.get_model("mail", "BouncedAddress")
    Outbound = apps.get_model("core", "OutboundEmail")
    State = apps.get_model("mail", "BounceAggregationState")
    # The simple unit pattern works on both PostgreSQL and Python-backed SQLite regular expressions.
    zero_size = Q(diagnostic_code__iregex=r"0([.]0+)?\s*([kmg]i?b|bytes?|k)")
    if reverse:
        candidate = zero_size & Q(category="transient", reason=ZERO_REASON)
    else:
        candidate = zero_size & Q(category="mailbox_disabled")
    if modern:
        ambiguous = Q(status_code__in=previous.AMBIGUOUS) | Q(diagnostic_code__regex=r"5[.]([24][.]1|4[.]4)([^0-9]|$)")
        candidate |= Q(category__in=("mailbox_disabled", "hard")) & ambiguous
        candidate |= Q(category="transient", reason=ZERO_REASON) & zero_size
    candidates = Bounce.objects.using(db).filter(candidate)
    if scope is not None:
        candidates = candidates.filter(scope)
    if not candidates.exists():
        return
    with transaction.atomic(using=db):
        if state is None:
            State.objects.using(db).get_or_create(source="graph")
            state = State.objects.using(db).select_for_update().get(source="graph")
        emails = set()
        for report in candidates.select_for_update().order_by("pk").iterator(chunk_size=500):
            verdict = corrected_verdict(report, reverse, modern)
            old = (report.classification, report.category, report.is_permanent, report.reason)
            if verdict is None or verdict == old:
                continue
            _adjust_aggregate(Address, report, state, old, verdict, db)
            report.classification, report.category, report.is_permanent, report.reason = verdict
            report.updated_at = timezone.now()
            report.save(using=db, update_fields=["category", "classification", "is_permanent", "reason", "updated_at"])
            if report.email_id:
                emails.add(report.email_id)
        for email_id in emails:
            kinds = Bounce.objects.using(db).filter(email_id=email_id).exclude(classification="delayed")
            worst = max(
                kinds.values_list("classification", flat=True), key=lambda kind: SEVERITY.get(kind, 0), default=""
            )
            Outbound.objects.using(db).filter(pk=email_id).update(bounce_classification=worst)
