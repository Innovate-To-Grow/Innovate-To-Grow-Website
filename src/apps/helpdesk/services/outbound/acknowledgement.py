"""The automatic acknowledgement of a new ticket (its number, so the requester can refer to it).

It goes to an address taken from inbound mail, so it must not become a relay for outsiders: it is sent only when the
sender passed DMARC (or Exchange's composite authentication), so a forged From never gets one; it passes
``shadow.automatic_reply_allowed`` (never for automated mail, spam, or a message that asks for no automatic reply);
it is never sent for backfilled mail or to one of the site's own addresses; at most once per ``ACK_WINDOW`` per
address and ``ACK_DAILY_CAP`` in all; and its text fills in no link the sender chose (``compose.fill``). It carries
``Auto-Submitted`` so responders do not answer it, and is no first response for the SLA.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.services.background_jobs import jobs_enabled
from apps.core.utils.security import is_plain_address

from ...models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ..tickets import events, shadow
from . import compose, jobs
from .replies import from_address, site_addresses

Kind = TicketMessage.Kind
ACK_WINDOW = timedelta(hours=24)
ACK_DAILY_CAP = 200
# Authentication-Results methods whose "pass" proves the From domain (DMARC, or Exchange's composite authentication).
_AUTHENTICATED = ("dmarc", "compauth")


def _authenticated(message: TicketMessage) -> bool:
    summary = message.auth_summary or {}
    return any(str(summary.get(method, "")).lower() == "pass" for method in _AUTHENTICATED)


def _acknowledgement_refused(address: str, now) -> bool:
    """At most ``ACK_DAILY_CAP`` acknowledgements a day in all, and one per address (newest first)."""
    recent = TicketMessage.objects.filter(kind=Kind.REPLY, automatic=True, occurred_at__gte=now - ACK_WINDOW)
    addresses = list(recent.order_by("-occurred_at").values_list("to_addresses", flat=True)[:ACK_DAILY_CAP])
    if len(addresses) >= ACK_DAILY_CAP:
        return True
    # JSON containment is not portable to SQLite, so the (at most ACK_DAILY_CAP) addresses are compared here.
    return any(address in (item or ()) for item in addresses)


def queue_acknowledgement(ticket: Ticket, message: TicketMessage, settings: HelpdeskSettings) -> TicketMessage | None:
    """The acknowledgement of the new ticket ``message`` opened, when it is switched on and allowed; else None.
    Call inside the transaction that stored the message: the send is queued when it commits."""
    if not settings.send_acknowledgement or ticket.backfilled or not jobs_enabled():
        return None
    if not shadow.automatic_reply_allowed(message, settings) or not _authenticated(message):
        return None
    address = ticket.requester_email
    if not is_plain_address(address) or address.lower() in site_addresses(ticket):
        return None
    now = timezone.now()
    if settings.pk:
        # Serialized on the settings row (the caller's transaction holds the lock), so two ingests at once cannot
        # both pass the per-address and daily limits.
        list(HelpdeskSettings.objects.select_for_update().filter(pk=settings.pk).values_list("pk", flat=True))
    if _acknowledgement_refused(address, now):
        return None
    ack = TicketMessage.objects.create(
        ticket=ticket,
        kind=Kind.REPLY,
        automatic=True,
        from_name="Innovate to Grow",
        from_address=from_address(),
        to_addresses=[address],
        subject=compose.reply_subject(ticket),
        occurred_at=now,
        body_text=compose.fill(settings.acknowledgement_text, ticket),
        delivery_status=TicketMessage.Delivery.QUEUED,
    )
    events.record(ticket, TicketEvent.Kind.ACKNOWLEDGED, to=address)
    transaction.on_commit(lambda: jobs.enqueue_reply(ack))
    return ack
