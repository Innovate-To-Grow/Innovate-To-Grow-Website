"""Saving the bounces of one report, idempotently, and marking the outgoing emails they prove failed.

Each (report, recipient) is saved once: its key is derived from the mailbox, the report's own Message-ID (or its
Graph id when it has none) and the recipient, and the key is unique in the table, so scanning a report again (the
scan overlap, a retried run, two workers) never adds a second row. A matched email's API status is left as it was
(it was accepted); only its delivery status moves to "failure confirmed" (or "delayed" while nothing worse is known).

A report is classified from what is stored (action, status code, scrubbed diagnostic), so it can be classified again
from the row alone: ``reclassify_stored`` after the rules change (Bounced addresses → Rebuild counts), and
``classify_unclassified`` for a report the previous release saved without a category while a deploy rolled out.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from django.db import IntegrityError, transaction
from django.db.models import DateTimeField, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import EmailBounce, OutboundEmail

from ..telemetry import text
from .classify import Verdict, classify
from .dsn import BounceReport, RecipientReport
from .matching import match

Classification = EmailBounce.Classification
Category = EmailBounce.Category
DeliveryStatus = OutboundEmail.DeliveryStatus
VERDICT_FIELDS = ("classification", "category", "is_permanent", "reason", "smtp_code")
# A stored report is always a failure or a delay; should one ever read as delivered, it is kept as unknown.
NO_VERDICT = Verdict(Classification.UNKNOWN, Category.UNKNOWN, None, "The report gives no status code")
SEVERITY = {
    Classification.HARD: 4,
    Classification.REJECTED: 3,
    Classification.SOFT: 2,
    Classification.UNKNOWN: 1,
    Classification.DELAYED: 0,
}


@dataclass
class SaveResult:
    created: list[EmailBounce] = field(default_factory=list)
    duplicates: int = 0
    ignored: int = 0

    @property
    def matched(self) -> int:
        return sum(1 for bounce in self.created if bounce.email_id is not None)


def verdict_values(verdict: Verdict) -> dict:
    """The fields of a stored report that its verdict sets."""
    reason = text.clean(verdict.reason, 255)
    values = (verdict.classification, verdict.category, verdict.is_permanent, reason, verdict.smtp_code)
    return dict(zip(VERDICT_FIELDS, values, strict=True))


def dedupe_key(mailbox: str, report_key: str, recipient: str) -> str:
    return hashlib.sha256("\n".join((mailbox, report_key, recipient)).encode("utf-8")).hexdigest()


def save_report(*, mailbox: str, graph_id: str, received_at: datetime, report: BounceReport) -> SaveResult:
    result = SaveResult()
    rows = report.recipients or (RecipientReport(""),)
    for row in rows:
        diagnostic = text.scrub(row.diagnostic, 1000)
        verdict = classify(row.action, row.status, diagnostic)
        if verdict is None:
            result.ignored += 1
            continue
        key = dedupe_key(mailbox, report.report_message_id or graph_id, row.recipient)
        if EmailBounce.objects.filter(dedupe_key=key).exists():
            result.duplicates += 1
            continue
        found = match(
            recipient=row.recipient,
            original_message_id=report.original_message_id,
            original_subject=report.original_subject,
            received_at=received_at,
        )
        values = {
            "mailbox": mailbox,
            "ndr_graph_id": graph_id[:512],
            "ndr_message_id": report.report_message_id[:255],
            "received_at": received_at,
            "bounced_at": row.last_attempt_at or report.arrival_at,
            "recipient": row.recipient[:254],
            "original_message_id": report.original_message_id[:255],
            # The original subject is shown only when the matched email's own subject is (never for credential
            # mail, whose subject may hold a login link); token-shaped text is scrubbed in any case.
            "original_subject": ""
            if found.email is not None and not found.email.subject
            else text.scrub(report.original_subject, 255),
            "action": row.action[:16],
            "status_code": row.status[:16],
            "diagnostic_code": diagnostic,
            "reporting_mta": report.reporting_mta[:255],
            "remote_mta": row.remote_mta[:255],
            **verdict_values(verdict),
            "email": found.email,
            "campaign_id": found.email.campaign_id if found.email is not None else None,
            "match_method": found.method,
            "match_note": text.clean(found.note, 255),
        }
        try:
            with transaction.atomic():
                bounce = EmailBounce.objects.create(dedupe_key=key, **values)
        except IntegrityError:
            result.duplicates += 1
            continue
        result.created.append(bounce)
        if found.email is not None:
            apply_to_email(found.email.pk, bounce)
    return result


def apply_to_email(email_id, bounce: EmailBounce) -> None:
    """Record on the email what the bounce proves; a later, milder report never softens an earlier verdict."""
    now = timezone.now()
    emails = OutboundEmail.objects.filter(pk=email_id)
    if bounce.classification == Classification.DELAYED:
        emails.exclude(delivery_status=DeliveryStatus.FAILURE_CONFIRMED).update(
            delivery_status=DeliveryStatus.DELAYED, updated_at=now
        )
        return
    current = emails.values_list("bounce_classification", flat=True).first()
    worst = bounce.classification
    if current and SEVERITY.get(current, 0) >= SEVERITY[worst]:
        worst = current
    emails.update(
        delivery_status=DeliveryStatus.FAILURE_CONFIRMED,
        bounce_classification=worst,
        bounced_at=Coalesce("bounced_at", Value(bounce.bounced_at or bounce.received_at, output_field=DateTimeField())),
        updated_at=now,
    )


def _apply_verdict(bounce: EmailBounce) -> bool:
    """Classify a stored report again from its own fields; whether its verdict changed."""
    values = verdict_values(classify(bounce.action, bounce.status_code, bounce.diagnostic_code) or NO_VERDICT)
    changed = any(getattr(bounce, name) != value for name, value in values.items())
    for name, value in values.items():
        setattr(bounce, name, value)
    return changed


def _save(rows: list[EmailBounce]) -> None:
    now = timezone.now()
    for row in rows:
        row.updated_at = now
    EmailBounce.objects.bulk_update(rows, [*VERDICT_FIELDS, "updated_at"])
    refresh_worst({row.email_id for row in rows if row.email_id is not None})


def reclassify_stored(*, batch_size: int = 500) -> int:
    """Classify every stored report again with the current rules, in batches; returns how many changed (the emails
    they are matched to get their worst classification again)."""
    changed, last = 0, None
    fields = ("pk", "email_id", "action", "status_code", "diagnostic_code", *VERDICT_FIELDS)
    while True:
        rows = EmailBounce.objects.order_by("pk").only(*fields)
        batch = list((rows if last is None else rows.filter(pk__gt=last))[: max(1, batch_size)])
        if not batch:
            return changed
        moved = [bounce for bounce in batch if _apply_verdict(bounce)]
        if moved:
            _save(moved)
        changed, last = changed + len(moved), batch[-1].pk


def classify_unclassified(*, batch_size: int = 500) -> int:
    """Classify every report saved without a category (by the release before categories, while a deploy rolled out),
    in batches; returns how many. Each gets a category, so the loop ends."""
    done = 0
    while rows := list(EmailBounce.objects.filter(category="").order_by("pk")[: max(1, batch_size)]):
        for bounce in rows:
            _apply_verdict(bounce)
        _save(rows)
        done += len(rows)
    return done


def refresh_worst(email_ids) -> None:
    """Set each email's worst bounce classification again from its stored reports (delays never count)."""
    for email_id in email_ids:
        kinds = EmailBounce.objects.filter(email_id=email_id).exclude(classification=Classification.DELAYED)
        worst = max(kinds.values_list("classification", flat=True), key=lambda kind: SEVERITY.get(kind, 0), default="")
        if worst:
            OutboundEmail.objects.filter(pk=email_id).update(bounce_classification=worst, updated_at=timezone.now())
