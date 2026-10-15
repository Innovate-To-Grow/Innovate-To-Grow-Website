"""Retention for the audited assistant conversations (public chat and AI search).

``SystemIntelligenceConfig.public_assistant_log_retention_days`` says how long a conversation is kept after its
last turn; 0 keeps everything. The ``system_intelligence_cleanup`` management command runs this. It is NOT part
of the background worker's scheduled maintenance: deleting audit records is a decision for whoever operates the
site, so it only happens when that command is run (by hand or from a scheduler they set up).
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.system_intelligence.models import AssistantConversationLog, SystemIntelligenceConfig

DEFAULT_BATCH_SIZE = 500


def conversation_log_retention_days() -> int:
    """The configured retention in days; 0 means keep forever.

    Without an active configuration ``load()`` hands back an unsaved object carrying the model defaults. A
    destructive cleanup must not act on a default nobody chose (the stored setting may be "keep forever" on a
    deactivated row), so that case keeps everything.
    """
    config = SystemIntelligenceConfig.load()
    if config.pk is None:
        return 0
    return int(config.public_assistant_log_retention_days or 0)


def purge_expired_conversation_logs(*, batch_size: int = DEFAULT_BATCH_SIZE, should_stop=None, now=None) -> int:
    """Delete conversations whose last turn is older than the retention window; return the rows deleted.

    The count includes the conversations' message rows, which go with them. Conversations are deleted oldest
    first in batches of ``batch_size``, each batch in its own transaction, so a large backlog never becomes one
    huge statement; ``should_stop`` is checked before every batch and ends the run with the finished batches
    committed.
    """
    retention_days = conversation_log_retention_days()
    if not retention_days:
        return 0

    try:
        cutoff = (now or timezone.now()) - timedelta(days=retention_days)
    except OverflowError:
        # A retention longer than the calendar reaches back: nothing can be older than it.
        return 0
    expired = AssistantConversationLog.objects.filter(last_activity_at__lt=cutoff)
    deleted = 0
    while True:
        if should_stop is not None and should_stop():
            break
        batch = list(expired.order_by("last_activity_at").values_list("pk", flat=True)[:batch_size])
        if not batch:
            break
        with transaction.atomic():
            removed, _per_model = AssistantConversationLog.objects.filter(pk__in=batch).delete()
        deleted += removed
        if len(batch) < batch_size:
            break
    return deleted
