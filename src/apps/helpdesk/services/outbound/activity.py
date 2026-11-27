"""Who is working a ticket, now that tickets have no owner (I2G-HELPDESK-01): every Admin works every ticket.

- **Last reply**: the latest reply staff wrote to the requester (``TicketMessage`` of ``Kind.REPLY``, not the automatic
  acknowledgement, and not one that failed to go out: the requester got nothing), by whom and when. The queue and the
  ticket page show it, so two people do not answer the same ticket unknowingly.
- **Replied since**: a reply someone else queued after a moment (when the reply form was shown). The reply form warns
  with it before sending (``outbound.replies.queue_reply``).
- **Awaiting a staff reply**: a person's ticket that is open and not waiting for the requester (New, In progress or
  On hold – awaiting internal), whose requester wrote after the last staff reply, or that nobody replied to yet. A
  requester's answer moves a ticket waiting for them back to In progress (``ingest.pipeline.messages``), so it is
  counted again then. The sidebar's Helpdesk badge counts them (``awaiting_reply_count``: one query, cached for
  ``AWAITING_CACHE_SECONDS``; ``admin.tickets.filters.awaiting_reply_badge``) and the queue's "Awaiting reply" view
  lists them.
"""

from django.core.cache import cache
from django.db.models import F, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from ...models import Ticket, TicketMessage

Status = Ticket.Status
Kind = TicketMessage.Kind
# Open, and the next move is staff's: waiting for the requester is not counted.
AWAITING_STATUSES = (Status.NEW, Status.OPEN, Status.PENDING_INTERNAL)
# The sidebar renders on every admin page: its count is shared for this long (one query per interval at most).
AWAITING_CACHE_SECONDS = 30
AWAITING_CACHE_KEY = "helpdesk:awaiting-reply-count"


def staff_replies() -> QuerySet:
    """Replies staff wrote to a requester that went out or may have (queued, sent or not confirmed)."""
    return TicketMessage.objects.filter(kind=Kind.REPLY, automatic=False).exclude(
        delivery_status=TicketMessage.Delivery.FAILED
    )


def _latest(messages: QuerySet, field: str) -> Subquery:
    return Subquery(messages.filter(ticket=OuterRef("pk")).order_by("-occurred_at", "-created_at").values(field)[:1])


def with_last_reply(queryset: QuerySet) -> QuerySet:
    """``queryset`` with ``last_reply_at`` and ``last_reply_by`` (the name the reply was sent under) of each ticket."""
    replies = staff_replies()
    return queryset.annotate(last_reply_at=_latest(replies, "occurred_at"), last_reply_by=_latest(replies, "from_name"))


def last_reply(ticket: Ticket) -> TicketMessage | None:
    return (
        staff_replies().filter(ticket=ticket).select_related("author").order_by("-occurred_at", "-created_at").first()
    )


def replied_by(message: TicketMessage) -> str:
    """Who wrote ``message``: the member's name now, else the name it was sent under."""
    author = message.author
    if author is not None:
        return author.get_full_name() or str(author)
    return message.from_name or "a former staff member"


def last_reply_text(ticket: Ticket) -> str:
    """The ticket page's "Last reply": by whom, when, and its delivery when it is not sent yet."""
    reply = last_reply(ticket) if ticket.pk else None
    if reply is None:
        return "Nobody has replied to the requester from the helpdesk yet."
    when = timezone.localtime(reply.occurred_at).strftime("%b %d, %Y %H:%M")
    state = "" if reply.delivery_status == TicketMessage.Delivery.SENT else f" ({reply.get_delivery_status_display()})"
    return f"{replied_by(reply)}, {when}{state}"


class ReplyCollision(Exception):
    """Someone else replied after the reply form was shown (``reply``); nothing was queued. Sent again from a page
    that shows that reply, it goes out."""

    def __init__(self, reply: TicketMessage):
        self.reply = reply
        self.by = replied_by(reply)
        when = timezone.localtime(reply.created_at).strftime("%b %d, %Y %H:%M")
        super().__init__(
            f"{self.by} replied to the requester at {when}, after you opened this ticket. Read their reply in the "
            "timeline, then send yours if it is still needed."
        )


def replied_since(ticket: Ticket, since, *, actor) -> TicketMessage | None:
    """The latest reply someone other than ``actor`` queued on ``ticket`` after ``since`` (None: nobody did)."""
    replies = staff_replies().filter(ticket=ticket, created_at__gt=since).select_related("author")
    if getattr(actor, "pk", None) is not None:
        replies = replies.exclude(author=actor)
    return replies.order_by("-created_at").first()


def awaiting_reply(queryset: QuerySet | None = None) -> QuerySet:
    """The tickets of ``queryset`` (every ticket by default) that await a staff reply (see the module docstring)."""
    queryset = Ticket.objects.all() if queryset is None else queryset
    customer = TicketMessage.objects.filter(kind=Kind.CUSTOMER)
    return (
        queryset.filter(automated=False, status__in=AWAITING_STATUSES)
        .annotate(
            awaiting_last_reply_at=_latest(staff_replies(), "occurred_at"),
            awaiting_last_customer_at=_latest(customer, "occurred_at"),
        )
        .filter(Q(awaiting_last_reply_at__isnull=True) | Q(awaiting_last_customer_at__gt=F("awaiting_last_reply_at")))
    )


def awaiting_reply_count(*, fresh: bool = False) -> int:
    """How many tickets await a staff reply (one query; shared for ``AWAITING_CACHE_SECONDS`` unless ``fresh``)."""
    if not fresh:
        cached = cache.get(AWAITING_CACHE_KEY)
        if isinstance(cached, int):
            return cached
    count = awaiting_reply().count()
    cache.set(AWAITING_CACHE_KEY, count, AWAITING_CACHE_SECONDS)
    return count
