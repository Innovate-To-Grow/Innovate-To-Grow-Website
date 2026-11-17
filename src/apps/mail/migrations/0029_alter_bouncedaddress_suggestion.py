"""Update review guidance and reclassify stored 0 KB receiving-limit reports.

The Graph counter is parked only when a report changed. Its next run rebuilds Graph counts from stored reports;
staff review state, suppression, SES counts and left-organisation notices are retained.

The reverse restores the classification used by the preceding release. This matters during a rollback: leaving the
stored rows as temporary while the old runtime classifies equivalent new reports as disabled would make aggregation
depend on which release happened to process a report.
"""

import re
import uuid
from datetime import UTC, datetime

from django.db import migrations, models
from django.utils import timezone

ZERO_LIMIT_RE = re.compile(
    r"\b(?:max(?:imum)?|limit|allowed)\b[^0-9.;]{0,40}?(?<![\d.])0(?:\.0+)? ?(?:[kmg]i?b|bytes?|k)\b"
)
ZERO_LIMIT_REASON = "Recipient mailbox reports a 0 KB limit; retry after the receiving service is fixed"
OLD_ZERO_LIMIT_REASON = "Recipient mailbox accepts no messages (0 KB size limit): treated as disabled"
PARKED = datetime(9999, 12, 31, tzinfo=UTC)
PARKED_ID = uuid.UUID(int=2**128 - 1)
SEVERITY = {"hard": 4, "rejected": 3, "soft": 2, "unknown": 1, "delayed": 0}


def _update_outbound_worst(Bounce, Outbound, db, email_ids):
    for email_id in email_ids:
        kinds = Bounce.objects.using(db).filter(email_id=email_id).exclude(classification="delayed")
        worst = max(kinds.values_list("classification", flat=True), key=lambda kind: SEVERITY.get(kind, 0), default="")
        Outbound.objects.using(db).filter(pk=email_id).update(bounce_classification=worst)


def _park_graph_counting(State, db):
    State.objects.using(db).update_or_create(source="graph", defaults={"cursor_at": PARKED, "cursor_id": PARKED_ID})


def reclassify_zero_limits(apps, schema_editor):
    db = schema_editor.connection.alias
    Bounce = apps.get_model("core", "EmailBounce")
    Outbound = apps.get_model("core", "OutboundEmail")
    State = apps.get_model("mail", "BounceAggregationState")
    changed, changed_count, email_ids = [], 0, set()
    reports = Bounce.objects.using(db).filter(category="mailbox_disabled", diagnostic_code__contains="0")
    for report in reports.iterator(chunk_size=500):
        if not ZERO_LIMIT_RE.search((report.diagnostic_code or "").lower()):
            continue
        report.category = "transient"
        report.classification = "soft"
        report.is_permanent = False
        report.reason = ZERO_LIMIT_REASON
        report.updated_at = timezone.now()
        changed.append(report)
        changed_count += 1
        if report.email_id is not None:
            email_ids.add(report.email_id)
        if len(changed) >= 500:
            Bounce.objects.using(db).bulk_update(
                changed, ["category", "classification", "is_permanent", "reason", "updated_at"]
            )
            changed.clear()
    if changed:
        Bounce.objects.using(db).bulk_update(
            changed, ["category", "classification", "is_permanent", "reason", "updated_at"]
        )
    _update_outbound_worst(Bounce, Outbound, db, email_ids)
    if changed_count:
        _park_graph_counting(State, db)


def restore_zero_limits(apps, schema_editor):
    """Restore the preceding release's classification for a safe rollback."""
    db = schema_editor.connection.alias
    Bounce = apps.get_model("core", "EmailBounce")
    Outbound = apps.get_model("core", "OutboundEmail")
    State = apps.get_model("mail", "BounceAggregationState")
    changed, changed_count, email_ids = [], 0, set()
    # ``reason`` is the marker written by the forward migration. A report could
    # already have been a legitimate transient 0 KB failure before this
    # migration; rolling back must not turn that unrelated row into a hard
    # mailbox-disabled bounce.
    reports = Bounce.objects.using(db).filter(
        category="transient", reason=ZERO_LIMIT_REASON, diagnostic_code__contains="0"
    )
    for report in reports.iterator(chunk_size=500):
        if not ZERO_LIMIT_RE.search((report.diagnostic_code or "").lower()):
            continue
        report.category = "mailbox_disabled"
        report.classification = "hard"
        report.is_permanent = True
        report.reason = OLD_ZERO_LIMIT_REASON
        report.updated_at = timezone.now()
        changed.append(report)
        changed_count += 1
        if report.email_id is not None:
            email_ids.add(report.email_id)
        if len(changed) >= 500:
            Bounce.objects.using(db).bulk_update(
                changed, ["category", "classification", "is_permanent", "reason", "updated_at"]
            )
            changed.clear()
    if changed:
        Bounce.objects.using(db).bulk_update(
            changed, ["category", "classification", "is_permanent", "reason", "updated_at"]
        )
    _update_outbound_worst(Bounce, Outbound, db, email_ids)
    if changed_count:
        _park_graph_counting(State, db)


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0028_bounced_address_notice_contact_hints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bouncedaddress",
            name="suggestion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("unsubscribe", "Unsubscribe: they reported us as spam"),
                    ("undeliverable", "Mark undeliverable or replace the address"),
                    (
                        "replace",
                        "Replace the address (the mailbox is disabled), or mark it undeliverable",
                    ),
                    (
                        "consider",
                        "Repeated temporary failures: check the receiving service, then retry this address",
                    ),
                    (
                        "relay",
                        "Our sending side: relay denied. Check our sending route and authorisation, then retry from another configured sender; the problem is not the address",
                    ),
                    (
                        "reputation",
                        "Our sending side: spam or reputation rejection. Check reputation, authentication and content, then retry from another configured sender; the problem is not the address",
                    ),
                    (
                        "policy",
                        "Their server's policy refused the message, not the address: no action",
                    ),
                    (
                        "left_org",
                        "May have left: an automatic reply says so. Check the notice, then replace the address or mark it undeliverable",
                    ),
                ],
                db_index=True,
                default="",
                max_length=16,
            ),
        ),
        migrations.RunPython(reclassify_zero_limits, restore_zero_limits),
    ]
