"""Replies to the requester (staff's "additional comments").

Nothing is sent while shadow mode is on (``tickets.shadow.sending_allowed``): the reply form is not offered and
``queue_reply`` refuses. A reply is stored on the ticket as a ``Kind.REPLY`` message and sent by the background job
``helpdesk.send_reply`` once the transaction commits (``jobs``), so a provider outage retries instead of losing it.
It is the ticket's first response once it is sent (not when queued: a reply that never goes out answers nobody), and
the status chosen with it is set at once. A reply quotes only the requester's own latest message with words of its
own (a merged ticket or a Cc'd participant never has someone else's words sent to them, nor staff's own reply quoted
back), and never goes to one of the site's own addresses or to a mailing list (it would reach all its members).
Staff's text is sent as written; only a personal sign-in link pasted into it is removed.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.core.services.background_jobs import jobs_enabled
from apps.core.utils.security import is_plain_address

from ...models import HelpdeskSettings, IntakeState, Ticket, TicketEvent, TicketMessage
from ..ingest.pipeline.messages import MAX_PARTICIPANTS
from ..ingest.routing.scam import own_words
from ..tickets import events, shadow
from ..tickets.scrub import scrub_sign_in_links
from . import compose, jobs
from .recipients import aliases, theirs, ticket_lists

Kind = TicketMessage.Kind
REPLY_MAX_CHARS = 20000
MAX_CC = 10
# The same text sent again this soon is a double submit (a reply that failed may be sent again at once).
DUPLICATE_WINDOW = timedelta(minutes=10)


class ReplyRefused(Exception):
    """The reply was not queued; the message says why (shown to staff as is)."""


def site_addresses(ticket: Ticket | None = None) -> frozenset[str]:
    """The site's own addresses: the From address, the Graph mailbox the site sends from, every mailbox the intake
    reads and (for ``ticket``) the mailbox its mail arrived in. Nothing the helpdesk sends goes to one of them."""
    from apps.core.models import MicrosoftGraphProviderConfig

    from_email = str(EmailServiceConfig.load().from_email or "")
    addresses = {from_email, MicrosoftGraphProviderConfig.load().sender_mailbox(from_email)}
    addresses.update(IntakeState.objects.values_list("mailbox", flat=True))
    if ticket is not None:
        addresses.update(_mailboxes(ticket))
    return frozenset(str(address).strip().lower() for address in addresses if address and str(address).strip())


def _mailboxes(ticket: Ticket) -> list[str]:
    received = TicketMessage.objects.filter(ticket=ticket, inbound__isnull=False).order_by("-created_at")
    return list(dict.fromkeys(received.values_list("inbound__mailbox", flat=True)))


def reply_mailbox(ticket: Ticket) -> str:
    """The mailbox the requester's mail arrived in ("" when unknown): their answer must reach it."""
    return next(iter(_mailboxes(ticket)), "")


def can_reply(ticket: Ticket, settings: HelpdeskSettings | None = None) -> str:
    """Why staff cannot reply to ``ticket`` now ("" when they can)."""
    if not shadow.sending_allowed(settings):
        return "Shadow mode is on: nothing is sent from the helpdesk. An I2G Master can switch it off in Helpdesk → Settings."
    if ticket.status == Ticket.Status.MERGED:
        return "This ticket was merged: reply on the ticket it was merged into."
    if ticket.is_automated_or_spam:
        return "Automated mail and spam are never answered from the helpdesk."
    if not is_plain_address(ticket.requester_email):
        return "The requester's address cannot be mailed (it is not a plain address)."
    if ticket.requester_email.lower() in site_addresses(ticket):
        return "The requester is one of the helpdesk's own addresses."
    if ticket.requester_email.lower() in ticket_lists(ticket):
        return (
            f"The requester {ticket.requester_email} is a mailing list: a reply would reach all its members. Write to "
            "the person from Outlook."
        )
    if not jobs_enabled():
        return "Background jobs are off, so a reply could not be delivered."
    return ""


def parse_cc(value: str, ticket: Ticket | None = None) -> list[str]:
    addresses = [item.strip().lower() for item in str(value or "").replace(";", ",").split(",") if item.strip()]
    if len(addresses) > MAX_CC:
        raise ReplyRefused(f"At most {MAX_CC} Cc addresses ({len(addresses)} given).")
    bad = next((address for address in addresses if not is_plain_address(address)), None)
    if bad is not None:
        raise ReplyRefused(f'"{bad}" in Cc is not a plain email address (use name@example.com, separated by commas).')
    own = next((address for address in addresses if address in site_addresses(ticket)), None)
    if own is not None:
        raise ReplyRefused(f"{own} is the helpdesk's own address: it is never copied on a reply.")
    listed = next((address for address in addresses if ticket is not None and address in ticket_lists(ticket)), None)
    if listed is not None:
        raise ReplyRefused(f"{listed} is a mailing list: a reply would reach all its members.")
    return list(dict.fromkeys(addresses))


def last_inbound(ticket: Ticket) -> TicketMessage | None:
    """The requester's own latest message on the ticket (quoted under a reply): from their address, written for them
    (a web form's), or from their other address under their name; never another sender's. One that only quotes
    (staff's own reply) is passed over."""
    if not ticket.requester_email:
        return None
    other = aliases(ticket)
    wanted = Q(on_behalf_of__iexact=ticket.requester_email) | Q(from_address__iexact=ticket.requester_email)
    for address in other:
        wanted |= Q(from_address__iexact=address)
    found = TicketMessage.objects.filter(wanted, ticket=ticket, kind=Kind.CUSTOMER).order_by(
        "-occurred_at", "-created_at"
    )
    candidates = [message for message in found[:20] if theirs(message, ticket, other)]
    said = (message for message in candidates if own_words(message.body_text, message.body_html).strip())
    return next(said, candidates[0] if candidates else None)


def from_address() -> str:
    return str(EmailServiceConfig.load().from_email or "")[:254]


def _text(body: str) -> str:
    text = scrub_sign_in_links(str(body or "").replace("\x00", "").replace("\r\n", "\n").strip())
    if not text:
        raise ReplyRefused("Write the reply before sending it.")
    if len(text) > REPLY_MAX_CHARS:
        raise ReplyRefused(f"A reply can be at most {REPLY_MAX_CHARS:,} characters ({len(text):,} written).")
    return text


def queue_reply(ticket: Ticket, *, actor, body: str, cc: str = "", status: str = "") -> TicketMessage:
    """Store a reply to the requester and queue its sending; ``status`` (optional) is set on the ticket with it."""
    from ..tickets import changes

    refusal = can_reply(ticket, HelpdeskSettings.load())
    if refusal:
        raise ReplyRefused(refusal)
    text = _text(body)
    requester = ticket.requester_email.lower()
    cc_list = [address for address in parse_cc(cc, ticket) if address != requester]
    now = timezone.now()
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        repeated = TicketMessage.objects.filter(
            ticket=current, kind=Kind.REPLY, automatic=False, author=actor, body_text=text
        ).filter(
            occurred_at__gte=now - DUPLICATE_WINDOW, delivery_status__in=(jobs.Delivery.QUEUED, jobs.Delivery.SENT)
        )
        if repeated.exists():
            raise ReplyRefused("This reply was already sent a moment ago (see the timeline); it was not sent twice.")
        message = TicketMessage.objects.create(
            ticket=current,
            kind=Kind.REPLY,
            author=actor,
            from_name=compose.person(actor)[:255],
            from_address=from_address(),
            to_addresses=[current.requester_email],
            cc_addresses=cc_list,
            subject=compose.reply_subject(current),
            occurred_at=now,
            body_text=text,
            delivery_status=TicketMessage.Delivery.QUEUED,
        )
        events.record(current, TicketEvent.Kind.REPLY, actor=actor, to=current.requester_email, cc=cc_list)
        Ticket.objects.filter(pk=current.pk).update(
            last_activity_at=max(current.last_activity_at, now),
            participants=list(dict.fromkeys([*current.participants, *cc_list]))[:MAX_PARTICIPANTS],
            updated_at=now,
        )
        if status and status != current.status:
            # The reply's own move out of New is no response yet: sending it is (``jobs``).
            changes.update_ticket(current, actor=actor, status=status, first_response=False)
        transaction.on_commit(lambda: jobs.enqueue_reply(message))
    return message
