"""Replies to the requester (staff's "additional comments") and the automatic acknowledgement of a new ticket.

Nothing is sent while shadow mode is on (``tickets.shadow.sending_allowed``): the reply form is not offered and
``queue_reply`` refuses. A reply is stored on the ticket as a ``Kind.REPLY`` message and sent by the background job
``helpdesk.send_reply`` once the transaction commits (``jobs``), so a provider outage retries instead of losing it.
It counts as the ticket's first response for the SLA. A reply quotes only the requester's own latest message (a merged
ticket or a Cc'd participant never has someone else's words sent to them).

The acknowledgement goes to an address taken from inbound mail, so it must not become a relay for outsiders: it is
sent only when the sender passed DMARC (or Exchange's composite authentication), so a forged From never gets one; it
passes ``shadow.automatic_reply_allowed`` (never for automated mail, spam, or a message that asks for no automatic
reply); it is never sent for backfilled mail; at most once per ``ACK_WINDOW`` per address and ``ACK_DAILY_CAP`` in
all; and its text fills in no link the sender chose (``compose.fill``). It carries ``Auto-Submitted`` so responders do
not answer it.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.core.services.background_jobs import jobs_enabled
from apps.core.services.email.inbound import scrub_links
from apps.core.utils.security import is_plain_address

from ...models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from .. import sla
from ..ingest.pipeline.messages import MAX_PARTICIPANTS
from ..tickets import events, shadow
from . import compose, jobs

Kind = TicketMessage.Kind
REPLY_MAX_CHARS = 20000
MAX_CC = 10
ACK_WINDOW = timedelta(hours=24)
ACK_DAILY_CAP = 200
# Authentication-Results methods whose "pass" proves the From domain (DMARC, or Exchange's composite authentication).
_AUTHENTICATED = ("dmarc", "compauth")


class ReplyRefused(Exception):
    """The reply was not queued; the message says why (shown to staff as is)."""


def can_reply(ticket: Ticket, settings: HelpdeskSettings | None = None) -> str:
    """Why staff cannot reply to ``ticket`` now ("" when they can)."""
    if not shadow.sending_allowed(settings):
        return "Shadow mode is on: nothing is sent from the helpdesk. Switch it off in Helpdesk → Settings."
    if ticket.status == Ticket.Status.MERGED:
        return "This ticket was merged: reply on the ticket it was merged into."
    if ticket.is_automated_or_spam:
        return "Automated mail and spam are never answered from the helpdesk."
    if not is_plain_address(ticket.requester_email):
        return "The requester's address cannot be mailed (it is not a plain address)."
    if ticket.requester_email.lower() == _from_address().lower():
        return "The requester is the helpdesk's own address."
    if not jobs_enabled():
        return "Background jobs are off, so a reply could not be delivered."
    return ""


def parse_cc(value: str) -> list[str]:
    addresses = [item.strip().lower() for item in str(value or "").replace(";", ",").split(",") if item.strip()]
    if len(addresses) > MAX_CC:
        raise ReplyRefused(f"At most {MAX_CC} Cc addresses.")
    if not all(is_plain_address(address) for address in addresses):
        raise ReplyRefused("Use plain email addresses such as name@example.com in Cc.")
    return list(dict.fromkeys(addresses))


def last_inbound(ticket: Ticket) -> TicketMessage | None:
    """The requester's own latest message on the ticket (quoted under a reply); never another sender's."""
    if not ticket.requester_email:
        return None
    return (
        TicketMessage.objects.filter(ticket=ticket, kind=Kind.CUSTOMER, from_address__iexact=ticket.requester_email)
        .order_by("-occurred_at", "-created_at")
        .first()
    )


def _from_address() -> str:
    return str(EmailServiceConfig.load().from_email or "")[:254]


def queue_reply(ticket: Ticket, *, actor, body: str, cc: str = "", status: str = "") -> TicketMessage:
    """Store a reply to the requester and queue its sending; ``status`` (optional) is set on the ticket with it."""
    from ..tickets import changes

    settings = HelpdeskSettings.load()
    refusal = can_reply(ticket, settings)
    if refusal:
        raise ReplyRefused(refusal)
    text = scrub_links(str(body or "").replace("\x00", "").strip())
    if not text:
        raise ReplyRefused("Write the reply before sending it.")
    if len(text) > REPLY_MAX_CHARS:
        raise ReplyRefused(f"A reply can be at most {REPLY_MAX_CHARS:,} characters.")
    requester = ticket.requester_email.lower()
    cc_list = [address for address in parse_cc(cc) if address != requester]
    now = timezone.now()
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        message = TicketMessage.objects.create(
            ticket=current,
            kind=Kind.REPLY,
            author=actor,
            from_name=compose.person(actor)[:255],
            from_address=_from_address(),
            to_addresses=[current.requester_email],
            cc_addresses=cc_list,
            subject=compose.reply_subject(current),
            occurred_at=now,
            body_text=text,
            delivery_status=TicketMessage.Delivery.QUEUED,
        )
        events.record(current, TicketEvent.Kind.REPLY, actor=actor, to=current.requester_email, cc=cc_list)
        updates = {
            "last_activity_at": max(current.last_activity_at, now),
            "participants": list(dict.fromkeys([*current.participants, *cc_list]))[:MAX_PARTICIPANTS],
            "updated_at": now,
        }
        responded = sla.responded_values(current, now)
        if responded:
            updates.update(responded)
            events.record(current, TicketEvent.Kind.RESPONDED, actor=actor, by="reply")
        Ticket.objects.filter(pk=current.pk).update(**updates)
        if status and status != current.status:
            changes.update_ticket(current, actor=actor, status=status)
        transaction.on_commit(lambda: jobs.enqueue_reply(message))
    return message


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
    if not is_plain_address(address) or address.lower() == _from_address().lower():
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
        from_address=_from_address(),
        to_addresses=[address],
        subject=compose.reply_subject(ticket),
        occurred_at=now,
        body_text=compose.fill(settings.acknowledgement_text, ticket),
        delivery_status=TicketMessage.Delivery.QUEUED,
    )
    events.record(ticket, TicketEvent.Kind.ACKNOWLEDGED, to=address)
    transaction.on_commit(lambda: jobs.enqueue_reply(ack))
    return ack
