"""Retention of email telemetry: outgoing emails (with their attempts) and bounce records older than their window
(``EMAIL_MONITORING["retention_days"]`` / ``["bounce_retention_days"]``) are deleted by the worker's maintenance."""

from datetime import timedelta

from django.utils import timezone

from apps.core.models import EmailBounce, OutboundEmail

from .recorder import monitoring_settings


def _purge(queryset, batch_size: int, should_stop) -> int:
    """Delete ``queryset`` in batches of primary keys; a stop request ends it after the batch in flight."""
    deleted = 0
    model = queryset.model
    while not (should_stop is not None and should_stop()):
        ids = list(queryset.values_list("pk", flat=True)[:batch_size])
        if not ids:
            break
        model.objects.filter(pk__in=ids).delete()
        deleted += len(ids)
    return deleted


def purge_expired(*, should_stop=None, now=None) -> dict[str, int]:
    """Delete expired telemetry; return how many emails and bounce records went (attempts go with their email, and
    a bounce kept longer than its email simply loses the link)."""
    config = monitoring_settings()
    now = now or timezone.now()
    batch_size = max(1, int(config["purge_batch_size"]))
    email_cutoff = now - timedelta(days=int(config["retention_days"]))
    bounce_cutoff = now - timedelta(days=int(config["bounce_retention_days"]))
    return {
        "emails": _purge(OutboundEmail.objects.filter(created_at__lt=email_cutoff), batch_size, should_stop),
        "bounces": _purge(EmailBounce.objects.filter(received_at__lt=bounce_cutoff), batch_size, should_stop),
    }
