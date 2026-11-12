"""Recording listed messages in the inbound queue, and the queue's retention.

``record`` is called by the app that lists the Inbox to fill the queue (the helpdesk's intake, on its own schedule
and checkpoint) for every message it lists; bounce processing reads the same Inbox separately and records nothing
here. Each (mailbox, Graph id) is recorded once: the scan's overlap lists a message again and again, and only the
first listing inserts a row. Recording is a single insert of bounded, cleaned values, so the content of a message can
never stall the scan; only a database outage fails it (and with it the scan, which keeps its progress).
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import DataError, IntegrityError, transaction
from django.db.models import DateTimeField
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import InboundMessage

from ..telemetry import text
from .scrub import scrub_subject

logger = logging.getLogger(__name__)


def record(mailbox: str, message: dict, received_at: datetime, *, candidate: bool, folder: str = "inbox") -> bool:
    """Record one listed message (a Graph ``message`` with the scan's fields); True when a new row was inserted."""
    graph_id = str(message.get("id") or "")[:512]
    if not graph_id or InboundMessage.objects.filter(mailbox=mailbox, graph_id=graph_id).exists():
        return False
    sender = (message.get("from") or {}).get("emailAddress") or {}
    values = {
        "folder": folder,
        # A NUL (which PostgreSQL text cannot hold) would make the row impossible to record, and the message be missed.
        "internet_message_id": text.message_id(str(message.get("internetMessageId") or "").replace("\x00", ""))[:255],
        "conversation_id": text.clean(message.get("conversationId"), 255),
        "received_at": received_at,
        "from_address": text.address(sender.get("address"))[:254],
        "from_name": scrub_subject(sender.get("name")),
        "subject": scrub_subject(message.get("subject")),
        "kind": InboundMessage.Kind.BOUNCE_CANDIDATE if candidate else InboundMessage.Kind.MESSAGE,
    }
    try:
        with transaction.atomic():
            InboundMessage.objects.create(mailbox=mailbox, graph_id=graph_id, **values)
    except IntegrityError:
        return False  # recorded by another process meanwhile
    except (DataError, ValueError, UnicodeError) as exc:
        # Values are cleaned and bounded; should the database still refuse one, the scan goes on without it.
        logger.warning("An inbound message could not be recorded (%s)", type(exc).__name__)
        return False
    return True


def pending_count() -> int:
    return InboundMessage.objects.filter(status=InboundMessage.Status.PENDING).count()


def retention_days() -> int:
    return max(1, int(settings.EMAIL_MONITORING["inbound_retention_days"]))


def purge_expired(*, now: datetime | None = None, should_stop=None) -> int:
    """Delete queue rows ``inbound_retention_days`` after they were processed (or, never processed, recorded), in
    batches; a stop request ends it after the batch in flight. What a consumer made of them stays (FKs are SET_NULL).

    A row waiting for its consumer counts from when it was recorded, not from when the mail arrived: a "Rescan since"
    of the helpdesk's intake (up to ``inbox_max_lookback_days`` back) records old mail, which must still wait to be
    imported."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=retention_days())
    batch_size = max(1, int(settings.EMAIL_MONITORING["purge_batch_size"]))
    expired = InboundMessage.objects.annotate(
        settled_at=Coalesce("processed_at", "created_at", output_field=DateTimeField())
    ).filter(settled_at__lt=cutoff)
    deleted = 0
    while not (should_stop is not None and should_stop()):
        ids = list(expired.exclude(status=InboundMessage.Status.PROCESSING).values_list("pk", flat=True)[:batch_size])
        if not ids:
            break
        InboundMessage.objects.filter(pk__in=ids).delete()
        deleted += len(ids)
    return deleted
