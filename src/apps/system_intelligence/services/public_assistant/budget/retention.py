"""Deleting expired database budget counters (and their reservations) in bounded batches."""

from django.db import transaction
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget


def purge_expired_public_assistant_budgets(*, batch_size: int = 1000) -> int:
    """Delete one bounded batch of expired database counters and reservations."""
    batch_size = max(1, int(batch_size))
    cutoff = timezone.now()
    with transaction.atomic():
        # Skip rows currently being reset/reserved. Rows locked here cannot be
        # reactivated between the expiry check and the cascading delete.
        expired_hashes = list(
            PublicAssistantTokenBudget.objects.select_for_update(skip_locked=True)
            .filter(window_expires_at__lte=cutoff)
            .order_by("window_expires_at")
            .values_list("pk", flat=True)[:batch_size]
        )
        if not expired_hashes:
            return 0
        _deleted_total, deleted_by_model = PublicAssistantTokenBudget.objects.filter(
            pk__in=expired_hashes,
            window_expires_at__lte=cutoff,
        ).delete()
        return int(deleted_by_model.get(PublicAssistantTokenBudget._meta.label, 0))
