"""Saving the bounces of one report, idempotently, and marking the outgoing emails they prove failed.

Each (report, recipient) is saved once: its key is derived from the mailbox, the report's own Message-ID (or its
Graph id when it has none) and the recipient, and the key is unique in the table, so scanning a report again (the
scan overlap, a retried run, two workers) never adds a second row. A matched email's API status is left as it was
(it was accepted); only its delivery status moves to "failure confirmed" (or "delayed" while nothing worse is known).
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
from .classify import classify
from .dsn import BounceReport, RecipientReport
from .matching import match

Classification = EmailBounce.Classification
DeliveryStatus = OutboundEmail.DeliveryStatus
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


def dedupe_key(mailbox: str, report_key: str, recipient: str) -> str:
    return hashlib.sha256("\n".join((mailbox, report_key, recipient)).encode("utf-8")).hexdigest()


def save_report(*, mailbox: str, graph_id: str, received_at: datetime, report: BounceReport) -> SaveResult:
    result = SaveResult()
    rows = report.recipients or (RecipientReport(""),)
    for row in rows:
        verdict = classify(row.action, row.status)
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
            "diagnostic_code": text.scrub(row.diagnostic, 1000),
            "reporting_mta": report.reporting_mta[:255],
            "remote_mta": row.remote_mta[:255],
            "classification": verdict.classification,
            "is_permanent": verdict.is_permanent,
            "reason": text.clean(verdict.reason, 255),
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
