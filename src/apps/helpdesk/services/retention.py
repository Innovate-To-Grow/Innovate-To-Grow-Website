"""The helpdesk's retention (the worker's hourly maintenance), with every period in ``HelpdeskSettings``.

In order: the bodies (text, HTML, attached messages) and attachments of automated mail after
``automated_retention_days`` and of spam after ``spam_retention_days``, counted from when the message arrived; the
bodies of every message of a closed ticket ``closed_body_retention_days`` after it closed, and its attachments after
``attachment_retention_days``; finally whole tickets (messages, attachments and events go with them)
``ticket_retention_days`` after they closed. A purged body keeps its metadata (sender, subject, dates) and says when
it was purged. Work is done in batches; a stop request ends it after the batch in flight.
"""

from datetime import timedelta

from django.conf import settings as django_settings
from django.db.models import Q
from django.utils import timezone

from ..models import HelpdeskSettings, Ticket, TicketAttachment, TicketMessage

CLOSED = Ticket.CLOSED_STATUSES


def _batch_size() -> int:
    return max(1, int(django_settings.EMAIL_MONITORING["purge_batch_size"]))


def _in_batches(queryset, apply, should_stop) -> int:
    done = 0
    batch_size = _batch_size()
    while not (should_stop is not None and should_stop()):
        ids = list(queryset.values_list("pk", flat=True)[:batch_size])
        if not ids:
            break
        apply(ids)
        done += len(ids)
    return done


def _purge_bodies(messages, now, should_stop) -> int:
    pending = messages.filter(body_purged_at__isnull=True)

    def apply(ids):
        TicketMessage.objects.filter(pk__in=ids).update(
            body_text="", body_html="", attached_messages=[], body_purged_at=now, updated_at=now
        )
        TicketAttachment.objects.filter(message_id__in=ids, purged_at__isnull=True).update(
            content=None, purged_at=now, updated_at=now
        )

    return _in_batches(pending, apply, should_stop)


def _purge_attachments(attachments, now, should_stop) -> int:
    def apply(ids):
        TicketAttachment.objects.filter(pk__in=ids).update(content=None, purged_at=now, updated_at=now)

    return _in_batches(attachments.filter(purged_at__isnull=True), apply, should_stop)


def purge_expired(*, now=None, should_stop=None) -> dict[str, int]:
    settings = HelpdeskSettings.load()
    now = now or timezone.now()

    def days(value) -> timedelta:
        return timedelta(days=int(value))

    automated = TicketMessage.objects.filter(
        kind=TicketMessage.Kind.AUTOMATED, occurred_at__lt=now - days(settings.automated_retention_days)
    )
    spam = TicketMessage.objects.filter(
        ticket__status=Ticket.Status.SPAM, occurred_at__lt=now - days(settings.spam_retention_days)
    )
    closed = Q(ticket__status__in=CLOSED, ticket__closed_at__lt=now - days(settings.closed_body_retention_days))
    old_files = Q(
        message__ticket__status__in=CLOSED,
        message__ticket__closed_at__lt=now - days(settings.attachment_retention_days),
    )
    expired_tickets = Ticket.objects.filter(status__in=CLOSED, closed_at__lt=now - days(settings.ticket_retention_days))
    result = {
        "automated_bodies": _purge_bodies(automated, now, should_stop),
        "spam_bodies": _purge_bodies(spam, now, should_stop),
        "closed_bodies": _purge_bodies(TicketMessage.objects.filter(closed), now, should_stop),
        "attachments": _purge_attachments(TicketAttachment.objects.filter(old_files), now, should_stop),
    }
    result["tickets"] = _in_batches(
        expired_tickets, lambda ids: Ticket.objects.filter(pk__in=ids).delete(), should_stop
    )
    return result
